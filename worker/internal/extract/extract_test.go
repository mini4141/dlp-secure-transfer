package extract

import (
	"archive/zip"
	"bytes"
	"fmt"
	"strings"
	"testing"
)

func TestPlainText(t *testing.T) {
	got, err := Text("a.csv", strings.NewReader("x,y\n1,2"))
	if err != nil || got != "x,y\n1,2" {
		t.Fatalf("got %q, %v", got, err)
	}
}

func TestUnsupported(t *testing.T) {
	if Supported("photo.png") {
		t.Fatal("png must be unsupported")
	}
	if _, err := Text("photo.png", strings.NewReader("")); err != ErrUnsupported {
		t.Fatalf("want ErrUnsupported, got %v", err)
	}
}

func TestDocx(t *testing.T) {
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	w, _ := zw.Create("word/document.xml")
	w.Write([]byte(`<w:document xmlns:w="x"><w:body><w:p><w:r><w:t>card 4111 1111 1111 1111</w:t></w:r></w:p></w:body></w:document>`))
	zw.Close()
	got, err := Text("f.docx", &buf)
	if err != nil || !strings.Contains(got, "4111 1111 1111 1111") {
		t.Fatalf("got %q, %v", got, err)
	}
}

func TestPDF(t *testing.T) {
	got, err := Text("f.pdf", bytes.NewReader(minimalPDF("card 4111 1111 1111 1111")))
	if err != nil || !strings.Contains(got, "4111") {
		t.Fatalf("got %q, %v", got, err)
	}
}

// minimalPDF builds a one-page PDF with a single line of text.
func minimalPDF(text string) []byte {
	var b bytes.Buffer
	var offs []int
	obj := func(s string) {
		offs = append(offs, b.Len())
		fmt.Fprintf(&b, "%d 0 obj\n%s\nendobj\n", len(offs), s)
	}
	b.WriteString("%PDF-1.4\n")
	obj("<< /Type /Catalog /Pages 2 0 R >>")
	obj("<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
	obj("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>")
	stream := fmt.Sprintf("BT /F1 12 Tf 72 720 Td (%s) Tj ET", text)
	obj(fmt.Sprintf("<< /Length %d >>\nstream\n%s\nendstream", len(stream), stream))
	obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
	xref := b.Len()
	fmt.Fprintf(&b, "xref\n0 %d\n0000000000 65535 f \n", len(offs)+1)
	for _, o := range offs {
		fmt.Fprintf(&b, "%010d 00000 n \n", o)
	}
	fmt.Fprintf(&b, "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n", len(offs)+1, xref)
	return b.Bytes()
}
