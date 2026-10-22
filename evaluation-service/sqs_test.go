package main

import (
	"errors"
	"testing"
)

func TestEnqueueComFilaCheia(t *testing.T) {
	publisher := &EventPublisher{
		events: make(chan EvaluationEvent, 1),
	}

	publisher.events <- EvaluationEvent{
		EventID: "evento-existente",
	}

	eventID, err := publisher.enqueue(
		"usuario-teste",
		"flag-teste",
		true,
	)

	if !errors.Is(err, errEventQueueFull) {
		t.Fatalf(
			"Esperava erro de fila cheia, recebi: %v",
			err,
		)
	}

	if eventID != "" {
		t.Fatalf(
			"Esperava eventID vazio, recebi: %s",
			eventID,
		)
	}
}
