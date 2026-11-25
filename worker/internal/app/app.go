// Package app wires the SQS consumer, S3 access, DLP scan and API callback.
package app

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"path"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	sqstypes "github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"

	"github.com/mini4141/dlp-secure-transfer/worker/internal/detect"
	"github.com/mini4141/dlp-secure-transfer/worker/internal/extract"
)

// Config is read from the environment by main.
type Config struct {
	Bucket       string
	QueueName    string
	APIURL       string
	HMACSecret   string
	ScanDelay    time.Duration
	MaxSamples   int
	HTTPClient   *http.Client
	S3           *s3.Client
	SQS          *sqs.Client
	WaitSeconds  int32
	queueURL     string
	callbackPath string
}

var (
	scansTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "dlp_worker_scans_total", Help: "Scans processed by result."}, []string{"result"})
	scanSeconds = promauto.NewHistogram(prometheus.HistogramOpts{
		Name: "dlp_worker_scan_seconds", Help: "Scan duration.", Buckets: prometheus.DefBuckets})
	tracer = otel.Tracer("dlp-worker")
)

// ScanMessage is the SQS body produced by the API on finalize.
type ScanMessage struct {
	ScanID   string `json:"scan_id"`
	FileID   int    `json:"file_id"`
	Key      string `json:"key"`
	Filename string `json:"filename"`
}

// Sample is an obfuscated snippet; raw PII never leaves the worker.
type Sample struct {
	Text string `json:"text"`
	Line int    `json:"line"`
}

// Finding aggregates one PII type for a file.
type Finding struct {
	Type    string   `json:"type"`
	Count   int      `json:"count"`
	Samples []Sample `json:"samples"`
}

// Result is POSTed to the API's internal endpoint.
type Result struct {
	ScanID      string    `json:"scan_id"`
	FileID      int       `json:"file_id"`
	Status      string    `json:"status"` // clean | findings | unscannable
	RedactedKey string    `json:"redacted_key,omitempty"`
	Findings    []Finding `json:"findings"`
}

// Run long-polls the queue until ctx is cancelled.
func Run(ctx context.Context, c *Config) error {
	c.callbackPath = "/internal/scan-results"
	for c.queueURL == "" {
		out, err := c.SQS.GetQueueUrl(ctx, &sqs.GetQueueUrlInput{QueueName: &c.QueueName})
		if err == nil {
			c.queueURL = *out.QueueUrl
			break
		}
		slog.Info("waiting for queue", "queue", c.QueueName, "err", err.Error())
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
	slog.Info("worker started", "queue", c.QueueName)
	for ctx.Err() == nil {
		out, err := c.SQS.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
			QueueUrl:                    &c.queueURL,
			MaxNumberOfMessages:         1,
			WaitTimeSeconds:             c.WaitSeconds,
			MessageAttributeNames:       []string{"All"},
			MessageSystemAttributeNames: []sqstypes.MessageSystemAttributeName{sqstypes.MessageSystemAttributeNameApproximateReceiveCount},
		})
		if err != nil {
			if ctx.Err() == nil {
				slog.Error("receive failed", "err", err.Error())
				time.Sleep(2 * time.Second)
			}
			continue
		}
		for _, m := range out.Messages {
			if err := c.handle(ctx, m); err != nil {
				// Not deleted: SQS redelivers after the visibility timeout; after
				// maxReceiveCount the message moves to the DLQ.
				slog.Error("scan failed, message left for redelivery", "err", err.Error())
				scansTotal.WithLabelValues("error").Inc()
			}
		}
	}
	return nil
}

func (c *Config) handle(ctx context.Context, m sqstypes.Message) error {
	carrier := propagation.MapCarrier{}
	for k, v := range m.MessageAttributes {
		if v.StringValue != nil {
			carrier[k] = *v.StringValue
		}
	}
	ctx = otel.GetTextMapPropagator().Extract(ctx, carrier)

	var msg ScanMessage
	if err := json.Unmarshal([]byte(aws.ToString(m.Body)), &msg); err != nil {
		return fmt.Errorf("bad message: %w", err)
	}
	ctx, span := tracer.Start(ctx, "dlp.scan", trace.WithSpanKind(trace.SpanKindConsumer),
		trace.WithAttributes(attribute.String("scan_id", msg.ScanID), attribute.Int("file_id", msg.FileID)))
	defer span.End()

	start := time.Now()
	receives := m.Attributes[string(sqstypes.MessageSystemAttributeNameApproximateReceiveCount)]
	slog.Info("scan received", "scan_id", msg.ScanID, "file_id", msg.FileID, "receive_count", receives)

	res, err := c.scan(ctx, msg)
	if err != nil {
		span.RecordError(err)
		return err
	}
	if err := c.post(ctx, res); err != nil {
		span.RecordError(err)
		return err
	}
	if _, err := c.SQS.DeleteMessage(ctx, &sqs.DeleteMessageInput{QueueUrl: &c.queueURL, ReceiptHandle: m.ReceiptHandle}); err != nil {
		return err
	}
	counts := map[string]int{}
	for _, f := range res.Findings {
		counts[f.Type] = f.Count
	}
	scansTotal.WithLabelValues(res.Status).Inc()
	scanSeconds.Observe(time.Since(start).Seconds())
	slog.Info("scan completed", "scan_id", msg.ScanID, "file_id", msg.FileID, "status", res.Status, "findings", counts)
	return nil
}

func (c *Config) scan(ctx context.Context, msg ScanMessage) (*Result, error) {
	res := &Result{ScanID: msg.ScanID, FileID: msg.FileID, Findings: []Finding{}}
	if !extract.Supported(msg.Filename) {
		res.Status = "unscannable"
		return res, nil
	}
	obj, err := c.S3.GetObject(ctx, &s3.GetObjectInput{Bucket: &c.Bucket, Key: &msg.Key})
	if err != nil {
		return nil, fmt.Errorf("get object: %w", err)
	}
	defer obj.Body.Close()
	text, err := extract.Text(msg.Filename, obj.Body)
	if err != nil {
		if errors.Is(err, extract.ErrUnsupported) {
			res.Status = "unscannable"
			return res, nil
		}
		return nil, fmt.Errorf("extract: %w", err)
	}
	if c.ScanDelay > 0 {
		slog.Info("simulated slow scan", "seconds", c.ScanDelay.Seconds())
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(c.ScanDelay):
		}
	}

	matches := detect.Find(text)
	res.Findings = aggregate(text, matches, c.MaxSamples)
	res.Status = "clean"
	if len(matches) == 0 {
		return res, nil
	}
	res.Status = "findings"

	redacted := detect.Redact(text, matches)
	rkey := "redacted/" + msg.Key
	ct := "text/plain; charset=utf-8"
	switch strings.ToLower(path.Ext(msg.Filename)) {
	case ".docx", ".pdf":
		rkey += ".txt"
	case ".csv":
		ct = "text/csv; charset=utf-8"
	case ".json":
		ct = "application/json"
	}
	_, err = c.S3.PutObject(ctx, &s3.PutObjectInput{
		Bucket: &c.Bucket, Key: &rkey, Body: bytes.NewReader([]byte(redacted)), ContentType: &ct,
	})
	if err != nil {
		return nil, fmt.Errorf("put redacted: %w", err)
	}
	res.RedactedKey = rkey
	return res, nil
}

func aggregate(text string, ms []detect.Match, maxSamples int) []Finding {
	byType := map[string]*Finding{}
	var order []string
	for _, m := range ms {
		f := byType[m.Type]
		if f == nil {
			f = &Finding{Type: m.Type, Samples: []Sample{}}
			byType[m.Type] = f
			order = append(order, m.Type)
		}
		f.Count++
		if len(f.Samples) < maxSamples {
			line := 1 + strings.Count(text[:m.Start], "\n")
			f.Samples = append(f.Samples, Sample{Text: detect.Obfuscate(m.Type, text[m.Start:m.End]), Line: line})
		}
	}
	out := make([]Finding, 0, len(order))
	for _, t := range order {
		out = append(out, *byType[t])
	}
	return out
}

// Sign returns the hex HMAC-SHA256 of body.
func Sign(secret string, body []byte) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(body)
	return hex.EncodeToString(h.Sum(nil))
}

func (c *Config) post(ctx context.Context, res *Result) error {
	body, _ := json.Marshal(res)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(c.APIURL, "/")+c.callbackPath, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Signature", Sign(c.HMACSecret, body))
	otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(req.Header))
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("post results: %w", err)
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("post results: status %d", resp.StatusCode)
	}
	return nil
}
