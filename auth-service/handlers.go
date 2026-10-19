package main

import (
	"context"
	"crypto/subtle"
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"strings"
	"time"
)

type CreateKeyRequest struct {
	Name string `json:"name"`
}

type CreateKeyResponse struct {
	Name    string `json:"name"`
	Key     string `json:"key"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, body interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	if err := json.NewEncoder(w).Encode(body); err != nil {
		log.Printf("Erro ao escrever resposta HTTP: %v", err)
	}
}

func bearerKey(r *http.Request) string {
	parts := strings.Fields(r.Header.Get("Authorization"))
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
		return ""
	}

	return parts[1]
}

func requireMethod(w http.ResponseWriter, r *http.Request, method string) bool {
	if r.Method == method {
		return true
	}

	w.Header().Set("Allow", method)
	writeJSON(w, http.StatusMethodNotAllowed, map[string]string{
		"error": "Metodo nao permitido",
	})
	return false
}

func (a *App) healthHandler(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodGet) {
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *App) readinessHandler(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodGet) {
		return
	}

	checkCtx, cancel := context.WithTimeout(r.Context(), time.Second)
	defer cancel()

	if err := a.DB.PingContext(checkCtx); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"status": "not ready",
		})
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (a *App) validateKeyHandler(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodGet) {
		return
	}

	key := bearerKey(r)
	if key == "" {
		w.Header().Set("WWW-Authenticate", "Bearer")
		writeJSON(w, http.StatusUnauthorized, map[string]string{
			"error": "Authorization Bearer obrigatorio",
		})
		return
	}

	queryCtx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	var id int
	err := a.DB.QueryRowContext(
		queryCtx,
		"SELECT id FROM api_keys WHERE key_hash = $1 AND is_active = true",
		hashAPIKey(key),
	).Scan(&id)

	if errors.Is(err, sql.ErrNoRows) {
		w.Header().Set("WWW-Authenticate", "Bearer")
		writeJSON(w, http.StatusUnauthorized, map[string]string{
			"error": "Chave de API invalida ou inativa",
		})
		return
	}

	if err != nil {
		log.Printf("Erro no banco durante validacao da chave: %v", err)
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "Servico de autenticacao temporariamente indisponivel",
		})
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{
		"message": "Chave valida",
	})
}

func (a *App) createKeyHandler(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, 4096)
	decoder := json.NewDecoder(r.Body)

	var req CreateKeyRequest
	if err := decoder.Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "Corpo da requisicao invalido ou muito grande",
		})
		return
	}

	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "Envie apenas um objeto JSON",
		})
		return
	}

	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "O campo name e obrigatorio",
		})
		return
	}

	newKey, err := generateAPIKey()
	if err != nil {
		log.Printf("Erro ao gerar chave: %v", err)
		writeJSON(w, http.StatusInternalServerError, map[string]string{
			"error": "Erro ao gerar chave",
		})
		return
	}

	queryCtx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	var newID int
	err = a.DB.QueryRowContext(
		queryCtx,
		"INSERT INTO api_keys (name, key_hash) VALUES ($1, $2) RETURNING id",
		req.Name,
		hashAPIKey(newKey),
	).Scan(&newID)

	if err != nil {
		log.Printf("Erro no banco durante criacao de chave: %v", err)
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "Nao foi possivel confirmar a criacao da chave",
		})
		return
	}

	log.Printf("Nova chave criada com sucesso: ID=%d", newID)
	writeJSON(w, http.StatusCreated, CreateKeyResponse{
		Name:    req.Name,
		Key:     newKey,
		Message: "Guarde esta chave; ela nao sera exibida novamente.",
	})
}

func (a *App) masterKeyAuthMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := bearerKey(r)

		if key == "" ||
			subtle.ConstantTimeCompare([]byte(key), []byte(a.MasterKey)) != 1 {
			writeJSON(w, http.StatusForbidden, map[string]string{
				"error": "Acesso nao autorizado",
			})
			return
		}

		next.ServeHTTP(w, r)
	})
}