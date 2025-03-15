// Simple Go program to process the model template included in Ollama's models
// This template language is using Go templates, so we cannot process them in Python
// but need a Go subprocess to create the prompt.
// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-CopyrightText: 2025 Gerhard Gappmeier <gappy1502@gmx.net>
// Disclaimer: I'm not a Go programmer and have created this little program
// using ChatGPT.
// Building: go build -o process_template process_template.go
package main

import (
    "bytes"
    "encoding/json"
    "text/template"
    "io"
    "log"
    "os"
)

func main() {
    // Read template from stdin
    templateData, err := io.ReadAll(os.Stdin)
    if err != nil {
        log.Fatal("Failed to read template:", err)
    }

    // Read input parameters (JSON from args)
    if len(os.Args) < 2 {
        log.Fatal("Usage: process_template '<json_input>'")
    }
    jsonInput := os.Args[1]

    // Parse JSON input
    var values map[string]string
    if err := json.Unmarshal([]byte(jsonInput), &values); err != nil {
        log.Fatal("Invalid JSON input:", err)
    }

    // Parse the Go template
    tmpl, err := template.New("template").Parse(string(templateData))
    if err != nil {
        log.Fatal("Failed to parse template:", err)
    }

    // Execute the template with the provided values
    var output bytes.Buffer
    if err := tmpl.Execute(&output, values); err != nil {
        log.Fatal("Failed to execute template:", err)
    }

    // Print the final processed output
    os.Stdout.Write(output.Bytes())
}

