
package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/go-redis/redis/v8"
)

func TestEvaluateComFilaDeAnalyticsCheia(t *testing.T) {
	// Cria um Redis simulado, sem usar o container real.
	redisServer := miniredis.RunT(t)

	redisClient := redis.NewClient(&redis.Options{
		Addr: redisServer.Addr(),
	})
	defer redisClient.Close()

	// Prepara uma flag habilitada no cache.
	// Sem regra de segmentacao, o resultado deve ser true.
	redisServer.Set(
		"flag_info:flag-teste",
		`{"Flag":{"name":"flag-teste","is_enabled":true},"Rule":null}`,
	)

	// Cria uma fila com capacidade 1 e a deixa cheia.
	publisher := &EventPublisher{
		events: make(chan EvaluationEvent, 1),
	}

	publisher.events <- EvaluationEvent{
		EventID: "evento-existente",
	}

	app := &App{
		RedisClient: redisClient,
		Publisher:   publisher,
	}

	// Simula uma requisicao ao endpoint /evaluate.
	request := httptest.NewRequest(
		http.MethodGet,
		"/evaluate?user_id=usuario-teste&flag_name=flag-teste",
		nil,
	)
	response := httptest.NewRecorder()

	app.evaluationHandler(response, request)

	// A fila cheia nao deve impedir a avaliacao.
	if response.Code != http.StatusOK {
		t.Fatalf(
			"Esperava HTTP 200, recebi %d: %s",
			response.Code,
			response.Body.String(),
		)
	}

	var body EvaluationResponse

	if err := json.NewDecoder(
		strings.NewReader(response.Body.String()),
	).Decode(&body); err != nil {
		t.Fatalf("Erro ao ler resposta JSON: %v", err)
	}

	if !body.Result {
		t.Fatal("Esperava resultado true para a flag habilitada")
	}

	if body.EventID != "" {
		t.Fatalf(
			"Esperava event_id vazio, recebi %q",
			body.EventID,
		)
	}
}
