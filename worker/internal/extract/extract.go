// Package extract turns supported file types into plain text.
package extract

import (
	"archive/zip"
	"bytes"
	"encoding/xml"
	"errors"
	"io"
	"path"
	"strings"

	"github.com/ledongthuc/pdf"
)

// ErrUnsupported marks a file type the worker cannot scan.
var ErrUnsupported = errors.New("unsupported file type")

// Supported reports whether a filename has a scannable extension.
func Supported(name string) bool {
	switch ext(name) {
	case ".txt", ".csv", ".json", ".md", ".docx", ".pdf":
		return true
	}
	return false
}

func ext(name string) string { return strings.ToLower(path.Ext(name)) }

// Text reads the whole object and returns its text. Plain-text formats are
// returned as-is; docx and pdf are decoded.
func Text(name string, r io.Reader) (string, error) {
	switch ext(name) {
	case ".txt", ".csv", ".json", ".md":
		b, err := io.ReadAll(r)
		return string(b), err
	case ".docx":
		b, err := io.ReadAll(r)
		if err != nil {
			return "", err
		}
		return docxText(b)
	case ".pdf":
		b, err := io.ReadAll(r)
		if err != nil {
			return "", err
		}
		return pdfText(b)
	}
	return "", ErrUnsupported
}

func docxText(b []byte) (string, error) {
	zr, err := zip.NewReader(bytes.NewReader(b), int64(len(b)))
	if err != nil {
		return "", err
	}
	for _, f := range zr.File {
		if f.Name != "word/document.xml" {
			continue
		}
		rc, err := f.Open()
		if err != nil {
			return "", err
		}
		defer rc.Close()
		dec := xml.NewDecoder(rc)
		var out strings.Builder
		inText := false
		for {
			tok, err := dec.Token()
			if err == io.EOF {
				break
			}
			if err != nil {
				return "", err
			}
			switch t := tok.(type) {
			case xml.StartElement:
				inText = t.Name.Local == "t"
			case xml.EndElement:
				inText = false
				if t.Name.Local == "p" {
					out.WriteByte('\n')
				}
			case xml.CharData:
				if inText {
					out.Write(t)
				}
			}
		}
		return out.String(), nil
	}
	return "", errors.New("word/document.xml not found")
}

func pdfText(b []byte) (string, error) {
	r, err := pdf.NewReader(bytes.NewReader(b), int64(len(b)))
	if err != nil {
		return "", err
	}
	pr, err := r.GetPlainText()
	if err != nil {
		return "", err
	}
	out, err := io.ReadAll(pr)
	return string(out), err
}
