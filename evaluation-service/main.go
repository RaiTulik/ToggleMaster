package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strings"
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
	SqsSvc              *sqs.SQS
	SqsQueueURL         string
	HttpClient          *http.Client
	FlagServiceURL      string
	TargetingServiceURL string
	ServiceAPIKey       string
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

	// Se um arquivo foi configurado, ele tem prioridade.
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

	sqsQueueURL := os.Getenv("AWS_SQS_URL")
	awsRegion := os.Getenv("AWS_REGION")

	if sqsQueueURL == "" {
		log.Println("AWS_SQS_URL nao definida. Eventos nao serao enviados.")
	}

	if awsRegion == "" && sqsQueueURL != "" {
		log.Fatal("AWS_REGION deve ser definida para usar SQS")
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("REDIS_URL invalida: %v", err)
	}

	rdb := redis.NewClient(opt)
	if _, err := rdb.Ping(ctx).Result(); err != nil {
		log.Fatalf("Nao foi possivel conectar ao Redis: %v", err)
	}
	defer rdb.Close()

	log.Println("Conectado ao Redis com sucesso!")

	var sqsSvc *sqs.SQS
	if sqsQueueURL != "" {
		awsConfig := &aws.Config{
			Region: aws.String(awsRegion),
		}

		if endpoint := os.Getenv("AWS_SQS_ENDPOINT"); endpoint != "" {
			awsConfig.Endpoint = aws.String(endpoint)
		}

		sess, err := session.NewSession(awsConfig)
		if err != nil {
			log.Fatalf("Nao foi possivel criar sessao AWS: %v", err)
		}

		sqsSvc = sqs.New(sess)
		log.Println("Cliente SQS inicializado com sucesso.")
	}

	app := &App{
		RedisClient:         rdb,
		SqsSvc:              sqsSvc,
		SqsQueueURL:         sqsQueueURL,
		HttpClient:          &http.Client{Timeout: 5 * time.Second},
		FlagServiceURL:      flagSvcURL,
		TargetingServiceURL: targetingSvcURL,
		ServiceAPIKey:       serviceAPIKey,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", app.healthHandler)
	mux.HandleFunc("/evaluate", app.evaluationHandler)

	log.Printf("Servico de Avaliacao rodando na porta %s", port)

	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatal(err)
	}
}