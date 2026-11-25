package app

import (
	"strings"
	"testing"

	"github.com/mini4141/dlp-secure-transfer/worker/internal/detect"
)

func TestAggregateKeepsOnlyObfuscatedSamples(t *testing.T) {
	text := "id,card\n1,4111 1111 1111 1111\n2,4242 4242 4242 4242\n"
	fs := aggregate(text, detect.Find(text), 1)
	if len(fs) != 1 || fs[0].Type != "card" || fs[0].Count != 2 || len(fs[0].Samples) != 1 {
		t.Fatalf("unexpected findings: %+v", fs)
	}
	s := fs[0].Samples[0]
	if s.Line != 2 || strings.Contains(s.Text, "1111 1111") {
		t.Fatalf("sample must be obfuscated and carry its line: %+v", s)
	}
}

func TestSignMatchesHMACSHA256(t *testing.T) {
	// python: hmac.new(b"secret", b"{}", sha256).hexdigest()
	want := "77325902caca812dc259733aacd046b73817372c777b8d95b402647474516e13"
	if got := Sign("secret", []byte("{}")); got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}
