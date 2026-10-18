FROM golang:1.26-bookworm AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -mod=readonly -trimpath -o /out/evaluation-service .

FROM scratch

COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /out/evaluation-service /evaluation-service

ENV PORT=8004

USER 10001:10001

EXPOSE 8004

ENTRYPOINT ["/evaluation-service"]