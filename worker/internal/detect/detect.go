// Package detect finds PII in text: emails, phone numbers, credit cards (Luhn),
// Japanese My Number (check digit) and IBANs (mod 97).
package detect

import (
	"regexp"
	"sort"
	"strings"
)

// Type names used in findings and in [REDACTED:<type>] markers.
const (
	TypeCard     = "card"
	TypeEmail    = "email"
	TypePhone    = "phone"
	TypeMyNumber = "my_number"
	TypeIBAN     = "iban"
)

// Match is one detected PII occurrence inside a text.
type Match struct {
	Type       string
	Start, End int // byte offsets in the scanned text
}

type detector struct {
	typ      string
	re       *regexp.Regexp
	validate func(string) bool
	claim    bool // an invalid candidate still blocks lower-priority detectors on that span
}

var detectors = []detector{
	{TypeIBAN, regexp.MustCompile(`\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b`), validIBAN, true},
	{TypeCard, regexp.MustCompile(`\b\d(?:[ -]?\d){12,18}\b`), validCard, true},
	{TypeMyNumber, regexp.MustCompile(`\b\d{4}[ -]?\d{4}[ -]?\d{4}\b`), validMyNumber, false},
	{TypeEmail, regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`), nil, false},
	{TypePhone, regexp.MustCompile(`\+[1-9](?:[ -]?\d){7,14}\b|\b0\d{1,4}-\d{1,4}-\d{4}\b`), nil, false},
}

// Find returns non-overlapping matches ordered by position. Detectors run in
// priority order so that a card number is never also reported as a phone number.
func Find(text string) []Match {
	var out, blocked []Match
	for _, d := range detectors {
		for _, loc := range d.re.FindAllStringIndex(text, -1) {
			s := text[loc[0]:loc[1]]
			if overlaps(out, loc[0], loc[1]) || overlaps(blocked, loc[0], loc[1]) {
				continue
			}
			if d.validate != nil && !d.validate(s) {
				if d.claim {
					blocked = append(blocked, Match{Start: loc[0], End: loc[1]})
				}
				continue
			}
			out = append(out, Match{Type: d.typ, Start: loc[0], End: loc[1]})
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Start < out[j].Start })
	return out
}

func overlaps(ms []Match, s, e int) bool {
	for _, m := range ms {
		if s < m.End && m.Start < e {
			return true
		}
	}
	return false
}

func digitsOnly(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func validCard(s string) bool {
	d := digitsOnly(s)
	if len(d) < 13 || len(d) > 19 {
		return false
	}
	return Luhn(d)
}

// Luhn reports whether the digit string passes the Luhn checksum.
func Luhn(d string) bool {
	sum, alt := 0, false
	for i := len(d) - 1; i >= 0; i-- {
		n := int(d[i] - '0')
		if alt {
			n *= 2
			if n > 9 {
				n -= 9
			}
		}
		sum += n
		alt = !alt
	}
	return sum%10 == 0
}

func validMyNumber(s string) bool {
	d := digitsOnly(s)
	return len(d) == 12 && MyNumberCheckDigit(d[:11]) == int(d[11]-'0')
}

// MyNumberCheckDigit computes the check digit for the first 11 digits of a
// Japanese Individual Number.
func MyNumberCheckDigit(first11 string) int {
	sum := 0
	for i := 0; i < 11; i++ {
		n := 11 - i // position counted from the right, 1..11 -> here p = 11-i
		q := n + 1
		if n >= 7 {
			q = n - 5
		}
		sum += int(first11[i]-'0') * q
	}
	r := sum % 11
	if r <= 1 {
		return 0
	}
	return 11 - r
}

func validIBAN(s string) bool {
	c := strings.ReplaceAll(s, " ", "")
	if len(c) < 15 || len(c) > 34 {
		return false
	}
	rearranged := c[4:] + c[:4]
	rem := 0
	for _, r := range rearranged {
		var v int
		switch {
		case r >= '0' && r <= '9':
			v = int(r - '0')
			rem = (rem*10 + v) % 97
		case r >= 'A' && r <= 'Z':
			v = int(r-'A') + 10
			rem = (rem*100 + v) % 97
		default:
			return false
		}
	}
	return rem == 1
}
