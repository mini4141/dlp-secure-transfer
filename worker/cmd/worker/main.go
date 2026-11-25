package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/smithy-go/logging"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"

	"github.com/mini4141/dlp-secure-transfer/worker/internal/app"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{ReplaceAttr: func(_ []string, a slog.Attr) slog.Attr {
		if a.Key == slog.TimeKey {
			a.Key = "ts"
		}
		if a.Key == slog.MessageKey {
			a.Key = "msg"
		}
		return a
	}})).With("service", "dlp-worker"))

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	shutdownTracing := initTracing(ctx)
	defer shutdownTracing()

	// Endpoint override (moto locally) comes only from AWS_ENDPOINT_URL, handled by the SDK.
	awsCfg, err := config.LoadDefaultConfig(ctx, config.WithLogger(logging.Nop{}))
	if err != nil {
		slog.Error("aws config", "err", err.Error())
		os.Exit(1)
	}
	delay, _ := strconv.Atoi(env("SCAN_DELAY_SECONDS", "0"))
	cfg := &app.Config{
		Bucket:      env("S3_BUCKET", "dlp-transfers"),
		QueueName:   env("SQS_QUEUE_NAME", "dlp-scan"),
		APIURL:      env("API_INTERNAL_URL", "http://localhost:8000"),
		HMACSecret:  os.Getenv("SCAN_HMAC_SECRET"),
		ScanDelay:   time.Duration(delay) * time.Second,
		MaxSamples:  5,
		HTTPClient:  &http.Client{Timeout: 15 * time.Second},
		S3:          s3.NewFromConfig(awsCfg, func(o *s3.Options) { o.UsePathStyle = os.Getenv("AWS_ENDPOINT_URL") != "" }),
		SQS:         sqs.NewFromConfig(awsCfg),
		WaitSeconds: 10,
	}

	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte("ok")) })
	srv := &http.Server{Addr: env("METRICS_ADDR", ":9090"), Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("metrics server", "err", err.Error())
		}
	}()

	if err := app.Run(ctx, cfg); err != nil && ctx.Err() == nil {
		slog.Error("worker stopped", "err", err.Error())
		os.Exit(1)
	}
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
	slog.Info("worker stopped")
}

// initTracing enables OTLP/HTTP export only when OTEL_EXPORTER_OTLP_ENDPOINT is set.
func initTracing(ctx context.Context) func() {
	otel.SetTextMapPropagator(propagation.TraceContext{})
	if os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT") == "" {
		return func() {}
	}
	exp, err := otlptracehttp.New(ctx)
	if err != nil {
		slog.Error("otlp exporter", "err", err.Error())
		return func() {}
	}
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(resource.NewWithAttributes(semconv.SchemaURL, semconv.ServiceName("dlp-worker"))),
	)
	otel.SetTracerProvider(tp)
	return func() {
		c, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = tp.Shutdown(c)
	}
}
