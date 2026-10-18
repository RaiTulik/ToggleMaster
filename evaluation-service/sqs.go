package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/sqs"
)

const (
	eventQueueCapacity = 256
	eventSenderCount   = 4
	eventSendTimeout   = 8 * time.Second
)

var (
	errPublisherStopped = errors.New("publicador de eventos encerrando")
	errEventQueueFull   = errors.New("fila interna de eventos cheia")
)

type EvaluationEvent struct {
	EventID   string    `json:"event_id"`
	UserID    string    `json:"user_id"`
	FlagName  string    `json:"flag_name"`
	Result    bool      `json:"result"`
	Timestamp time.Time `json:"timestamp"`
}

type EventPublisher struct {
	client   *sqs.SQS
	queueURL string
	events   chan EvaluationEvent

	mu      sync.RWMutex
	stopped bool

	ctx    context.Context
	cancel context.CancelFunc
	done   chan struct{}
}

func newEventPublisher(client *sqs.SQS, queueURL string) *EventPublisher {
	ctx, cancel := context.WithCancel(context.Background())

	publisher := &EventPublisher{
		client:   client,
		queueURL: queueURL,
		events:   make(chan EvaluationEvent, eventQueueCapacity),
		ctx:      ctx,
		cancel:   cancel,
		done:     make(chan struct{}),
	}

	var workers sync.WaitGroup
	workers.Add(eventSenderCount)

	for i := 0; i < eventSenderCount; i++ {
		go func() {
			defer workers.Done()

			for event := range publisher.events {
				if publisher.ctx.Err() != nil {
					log.Printf(
						"Evento nao enviado durante encerramento: event_id=%s",
						event.EventID,
					)
					continue
				}

				publisher.send(event)
			}
		}()
	}

	go func() {
		workers.Wait()
		close(publisher.done)
	}()

	return publisher
}

func (p *EventPublisher) enqueue(
	userID string,
	flagName string,
	result bool,
) (string, error) {
	randomBytes := make([]byte, 16)
	if _, err := rand.Read(randomBytes); err != nil {
		return "", err
	}

	event := EvaluationEvent{
		EventID:   hex.EncodeToString(randomBytes),
		UserID:    userID,
		FlagName:  flagName,
		Result:    result,
		Timestamp: time.Now().UTC(),
	}

	// Impede fechar o canal enquanto uma requisicao tenta inserir.
	p.mu.RLock()
	defer p.mu.RUnlock()

	if p.stopped {
		return "", errPublisherStopped
	}

	select {
	case p.events <- event:
		return event.EventID, nil
	default:
		return "", errEventQueueFull
	}
}

func (p *EventPublisher) send(event EvaluationEvent) {
	body, err := json.Marshal(event)
	if err != nil {
		log.Printf(
			"Falha ao serializar evento: event_id=%s erro=%v",
			event.EventID,
			err,
		)
		return
	}

	ctx, cancel := context.WithTimeout(p.ctx, eventSendTimeout)
	defer cancel()

	_, err = p.client.SendMessageWithContext(
		ctx,
		&sqs.SendMessageInput{
			MessageBody: aws.String(string(body)),
			QueueUrl:    aws.String(p.queueURL),
		},
	)

	if err != nil {
		log.Printf(
			"Falha ao enviar evento para SQS: event_id=%s erro=%v",
			event.EventID,
			err,
		)
		return
	}

	log.Printf(
		"Evento enviado para SQS: event_id=%s flag=%s",
		event.EventID,
		event.FlagName,
	)
}

func (p *EventPublisher) stop(ctx context.Context) error {
	p.mu.Lock()
	if !p.stopped {
		p.stopped = true
		close(p.events)
	}
	p.mu.Unlock()

	select {
	case <-p.done:
		p.cancel()
		return nil

	case <-ctx.Done():
		p.cancel()
		<-p.done
		return ctx.Err()
	}
}