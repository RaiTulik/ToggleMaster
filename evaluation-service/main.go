package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/sqs"
	"github.com/go-redis/redis/v8"
	"github.com/joho/godotenv"
)

var ctx = context.Background()

type App struct {
	RedisClient         *redis.Client
	HttpClient          *http.Client
	FlagServiceURL      string
	TargetingServiceURL string
	ServiceAPIKey       string
	Publisher           *EventPublisher
	ShuttingDown        atomic.Bool
}

func main() {
	_ = godotenv.Load()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8004"
	}

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		log.Fatal("REDIS_URL deve ser definida")
	}

	flagSvcURL := os.Getenv("FLAG_SERVICE_URL")
	if flagSvcURL == "" {
		log.Fatal("FLAG_SERVICE_URL deve ser definida")
	}

	targetingSvcURL := os.Getenv("TARGETING_SERVICE_URL")
	if targetingSvcURL == "" {
		log.Fatal("TARGETING_SERVICE_URL deve ser definida")
	}

	serviceAPIKey := strings.TrimSpace(os.Getenv("SERVICE_API_KEY"))

	if keyFile := os.Getenv("SERVICE_API_KEY_FILE"); keyFile != "" {
		keyBytes, err := os.ReadFile(keyFile)
		if err != nil {
			log.Fatalf("Nao foi possivel ler SERVICE_API_KEY_FILE: %v", err)
		}
		serviceAPIKey = strings.TrimSpace(string(keyBytes))
	}

	if serviceAPIKey == "" {
		log.Fatal("Defina SERVICE_API_KEY ou um SERVICE_API_KEY_FILE valido")
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("REDIS_URL invalida: %v", err)
	}

	rdb := redis.NewClient(opt)
	defer rdb.Close()

	pingCtx, cancelPing := context.WithTimeout(context.Background(), 3*time.Second)
	_, err = rdb.Ping(pingCtx).Result()
	cancelPing()

	if err != nil {
		log.Fatalf("Nao foi possivel conectar ao Redis: %v", err)
	}

	log.Println("Conectado ao Redis com sucesso!")

	app := &App{
		RedisClient:         rdb,
		HttpClient:          &http.Client{Timeout: 5 * time.Second},
		FlagServiceURL:      flagSvcURL,
		TargetingServiceURL: targetingSvcURL,
		ServiceAPIKey:       serviceAPIKey,
	}

	sqsQueueURL := os.Getenv("AWS_SQS_URL")
	if sqsQueueURL != "" {
		awsRegion := os.Getenv("AWS_REGION")
		if awsRegion == "" {
			log.Fatal("AWS_REGION deve ser definida para usar SQS")
		}

		awsConfig := &aws.Config{
			Region:     aws.String(awsRegion),
			MaxRetries: aws.Int(2),
			HTTPClient: &http.Client{Timeout: 8 * time.Second},
		}

		if endpoint := os.Getenv("AWS_SQS_ENDPOINT"); endpoint != "" {
			awsConfig.Endpoint = aws.String(endpoint)
		}

		sess, err := session.NewSession(awsConfig)
		if err != nil {
			log.Fatalf("Nao foi possivel criar sessao AWS: %v", err)
		}

		app.Publisher = newEventPublisher(sqs.New(sess), sqsQueueURL)
		log.Println("Publicador SQS iniciado com quatro enviadores.")
	} else {
		log.Println("AWS_SQS_URL ausente: publicacao de eventos desativada.")
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", app.healthHandler)
	mux.HandleFunc("/ready", app.readinessHandler)
	mux.HandleFunc("/evaluate", app.evaluationHandler)

	server := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	signalCtx, stopSignals := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stopSignals()

	serverErrors := make(chan error, 1)

	go func() {
		log.Printf("Servico de Avaliacao rodando na porta %s", port)
		serverErrors <- server.ListenAndServe()
	}()

	select {
	case <-signalCtx.Done():
		log.Println("Sinal de encerramento recebido.")

	case err := <-serverErrors:
		if !errors.Is(err, http.ErrServerClosed) {
			log.Printf("Servidor HTTP interrompido: %v", err)
		}
	}

	app.ShuttingDown.Store(true)

	// Para de aceitar conexoes e aguarda requisicoes em andamento.
	shutdownCtx, cancelShutdown := context.WithTimeout(
		context.Background(),
		10*time.Second,
	)

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("Prazo de encerramento HTTP atingido: %v", err)
		_ = server.Close()
	}
	cancelShutdown()

	// Depois das requisicoes, tenta concluir os eventos pendentes.
	if app.Publisher != nil {
		drainCtx, cancelDrain := context.WithTimeout(
			context.Background(),
			30*time.Second,
		)

		if err := app.Publisher.stop(drainCtx); err != nil {
			log.Printf("Encerramento com eventos nao enviados: %v", err)
		} else {
			log.Println("Publicador encerrado; tentativas pendentes concluidas.")
		}
		cancelDrain()
	}

	log.Println("Evaluation encerrado.")
}