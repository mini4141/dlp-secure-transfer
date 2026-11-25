package detect

import "strings"

// Obfuscate masks a raw match for display: `4111 **** **** 1111`, `ta***@example.com`.
func Obfuscate(typ, raw string) string {
	switch typ {
	case TypeEmail:
		at := strings.LastIndex(raw, "@")
		keep := 2
		if at < keep {
			keep = at
		}
		return raw[:keep] + "***" + raw[at:]
	case TypeCard:
		return maskDigits(raw, 4, 4)
	case TypeMyNumber:
		return maskDigits(raw, 0, 4)
	case TypePhone:
		return maskDigits(raw, 0, 2)
	case TypeIBAN:
		c := strings.ReplaceAll(raw, " ", "")
		return c[:4] + strings.Repeat("*", len(c)-8) + c[len(c)-4:]
	}
	return "***"
}

// maskDigits replaces digits with '*' except the first `head` and last `tail` digits,
// keeping separators in place.
func maskDigits(s string, head, tail int) string {
	total := 0
	for _, r := range s {
		if r >= '0' && r <= '9' {
			total++
		}
	}
	var b strings.Builder
	seen := 0
	for _, r := range s {
		if r >= '0' && r <= '9' {
			if seen < head || seen >= total-tail {
				b.WriteRune(r)
			} else {
				b.WriteByte('*')
			}
			seen++
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

// Redact replaces every match in text with [REDACTED:<type>].
func Redact(text string, ms []Match) string {
	if len(ms) == 0 {
		return text
	}
	var b strings.Builder
	last := 0
	for _, m := range ms {
		b.WriteString(text[last:m.Start])
		b.WriteString("[REDACTED:" + m.Type + "]")
		last = m.End
	}
	b.WriteString(text[last:])
	return b.String()
}
