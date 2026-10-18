package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strings"
	"time"
)

type EvaluationResponse struct {
	FlagName string `json:"flag_name"`
	UserID   string `json:"user_id"`
	Result   bool   `json:"result"`
	EventID  string `json:"event_id,omitempty"`
}

func writeJSON(w http.ResponseWriter, status int, body interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		log.Printf("Erro ao escrever resposta HTTP: %v", err)
	}
}

func requireGET(w http.ResponseWriter, r *http.Request) bool {
	if r.Method == http.MethodGet {
		return true
	}

	w.Header().Set("Allow", http.MethodGet)
	writeJSON(w, http.StatusMethodNotAllowed, map[string]string{
		"error": "Metodo nao permitido",
	})
	return false
}

func (a *App) healthHandler(w http.ResponseWriter, r *http.Request) {
	if !requireGET(w, r) {
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *App) readinessHandler(w http.ResponseWriter, r *http.Request) {
	if !requireGET(w, r) {
		return
	}

	if a.ShuttingDown.Load() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"status": "encerrando",
		})
		return
	}

	checkCtx, cancel := context.WithTimeout(r.Context(), time.Second)
	defer cancel()

	if err := a.RedisClient.Ping(checkCtx).Err(); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"status": "redis indisponivel",
		})
		return
	}

	if a.Publisher != nil {
		a.Publisher.mu.RLock()
		unavailable := a.Publisher.stopped ||
			len(a.Publisher.events) == cap(a.Publisher.events)
		a.Publisher.mu.RUnlock()

		if unavailable {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{
				"status": "publicador indisponivel",
			})
			return
		}
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (a *App) evaluationHandler(w http.ResponseWriter, r *http.Request) {
	if !requireGET(w, r) {
		return
	}

	if a.ShuttingDown.Load() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "Servico encerrando",
		})
		return
	}

	userID := strings.TrimSpace(r.URL.Query().Get("user_id"))
	flagName := strings.TrimSpace(r.URL.Query().Get("flag_name"))

	if userID == "" || flagName == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "user_id e flag_name sao obrigatorios",
		})
		return
	}

	if len(userID) > 256 || len(flagName) > 100 {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "user_id deve ter ate 256 bytes e flag_name ate 100 bytes",
		})
		return
	}

	result, err := a.getDecision(userID, flagName)
	if err != nil {
		var notFound *NotFoundError
		if errors.As(err, &notFound) {
			result = false
		} else {
			log.Printf("Erro ao avaliar flag %q: %v", flagName, err)
			writeJSON(w, http.StatusBadGateway, map[string]string{
				"error": "Erro ao consultar os servicos da flag",
			})
			return
		}
	}

	eventID := ""
	if a.Publisher != nil {
		eventID, err = a.Publisher.enqueue(userID, flagName, result)
		if err != nil {
			if errors.Is(err, errEventQueueFull) ||
				errors.Is(err, errPublisherStopped) {
				w.Header().Set("Retry-After", "1")
				writeJSON(w, http.StatusServiceUnavailable, map[string]string{
					"error": "Publicador ocupado ou encerrando; tente novamente",
				})
				return
			}

			log.Printf("Erro ao preparar evento: %v", err)
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "Erro ao preparar evento",
			})
			return
		}
	} else {
		log.Printf(
			"[SQS_DISABLED] Avaliacao: usuario=%q flag=%q resultado=%t",
			userID, flagName, result,
		)
	}

	writeJSON(w, http.StatusOK, EvaluationResponse{
		FlagName: flagName,
		UserID:   userID,
		Result:   result,
		EventID:  eventID,
	})
}