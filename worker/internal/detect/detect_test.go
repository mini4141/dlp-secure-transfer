package detect

import (
	"strings"
	"testing"
)

func types(ms []Match) []string {
	var out []string
	for _, m := range ms {
		out = append(out, m.Type)
	}
	return out
}

func one(t *testing.T, text, want string) Match {
	t.Helper()
	ms := Find(text)
	if len(ms) != 1 || ms[0].Type != want {
		t.Fatalf("Find(%q) = %v, want one %s", text, types(ms), want)
	}
	return ms[0]
}

func TestCardLuhn(t *testing.T) {
	one(t, "card 4111 1111 1111 1111 end", TypeCard)
	if got := Find("card 4111 1111 1111 1112"); len(got) != 0 {
		t.Fatalf("invalid Luhn must not match, got %v", types(got))
	}
}

func TestEmail(t *testing.T) {
	one(t, "mail taro@example.com now", TypeEmail)
}

func TestPhone(t *testing.T) {
	one(t, "call +81 90 1234 5678 please", TypePhone)
	one(t, "call 03-1234-5678 please", TypePhone)
}

func TestMyNumberCheckDigit(t *testing.T) {
	first := "12345678901"
	valid := first + string(rune('0'+MyNumberCheckDigit(first)))
	one(t, "mynumber "+valid, TypeMyNumber)
	bad := first + string(rune('0'+(MyNumberCheckDigit(first)+1)%10))
	if got := Find("mynumber " + bad); len(got) != 0 {
		t.Fatalf("bad check digit must not match, got %v", types(got))
	}
}

func TestIBAN(t *testing.T) {
	one(t, "iban GB82 WEST 1234 5698 7654 32 ok", TypeIBAN)
	if got := Find("iban GB82 WEST 1234 5698 7654 33"); len(got) != 0 {
		t.Fatalf("bad mod97 must not match, got %v", types(got))
	}
}

func TestObfuscateAndRedact(t *testing.T) {
	if got := Obfuscate(TypeCard, "4111 1111 1111 1111"); got != "4111 **** **** 1111" {
		t.Fatalf("card obfuscation: %s", got)
	}
	if got := Obfuscate(TypeEmail, "taro@example.com"); got != "ta***@example.com" {
		t.Fatalf("email obfuscation: %s", got)
	}
	text := "pay 4111 1111 1111 1111 to taro@example.com"
	red := Redact(text, Find(text))
	if red != "pay [REDACTED:card] to [REDACTED:email]" {
		t.Fatalf("redact: %s", red)
	}
	if strings.Contains(red, "4111") {
		t.Fatal("redacted text leaks PII")
	}
}
