package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
)

func main() {
	port := "8080"
	if len(os.Args) > 1 {
		port = os.Args[1]
	}

	// Get current directory
	dir, err := os.Getwd()
	if err != nil {
		log.Fatal(err)
	}

	// Create file server
	fs := http.FileServer(http.Dir(dir))

	// Add WASM MIME type support
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// Set WASM MIME type
		if filepath.Ext(r.URL.Path) == ".wasm" {
			w.Header().Set("Content-Type", "application/wasm")
		}
		
		// Add CORS headers for development
		w.Header().Set("Cross-Origin-Embedder-Policy", "require-corp")
		w.Header().Set("Cross-Origin-Opener-Policy", "same-origin")
		
		fs.ServeHTTP(w, r)
	})

	fmt.Printf("🚀 AudioPipe WASM Server starting on http://localhost:%s\n", port)
	fmt.Printf("📁 Serving files from: %s\n", dir)
	fmt.Printf("🌐 Open http://localhost:%s in your browser\n", port)
	fmt.Printf("⏹️  Press Ctrl+C to stop\n\n")

	log.Fatal(http.ListenAndServe(":"+port, nil))
}
