# Etapa 1: compilar a aplicação
FROM golang:1.26-bookworm AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -mod=readonly -trimpath -o /out/auth-service .

# Etapa 2: executar a aplicação
FROM scratch

COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /out/auth-service /auth-service

ENV PORT=8001

USER 10001:10001

EXPOSE 8001

ENTRYPOINT ["/auth-service"]