#!/usr/bin/env python3
import subprocess
import sys
import shutil

# ----------------------------
# Configuration
# ----------------------------

# Prompt to send into complete.py
TEST_PROMPT = "int main(int <FILL_IN_HERE>)"

# What we expect the model to output (substring match)
EXPECTED = "argc, char *argv[]"

# limit number of tokens for fast generation, temp=0 for reproducible results
OPTIONS = '{ "temperature": 0, "top_p": 0.95, "max_tokens": 10 }'

# Models to test per provider
MODELS = {
    "ollama": [
        "mistral:7b",
        "qwen2.5-coder:1.5b",
        "starcoder2:3b",
        "codegeex4:latest",
    ],
    "openai_legacy": [
        "gpt-3.5-turbo-instruct",
    ],
    "openai": [
        "gpt-4.1-mini",
        "gpt-4.1",
    ],
    "mistral": [
        "codestral-2501",
    ],
}

# Ollama endpoint
OLLAMA_URL = "http://tux:11434"

# Path to the completion script
COMPLETE = "./complete.py"

# Time until subprocess is killed
TIMEOUT_SECONDS = 30


# ----------------------------
# Runner
# ----------------------------

def run_completion(provider, model):
    """Run complete.py for one provider+model."""
    cmd = [COMPLETE, "-p", provider, "-m", model]

    # Only Ollama needs URL
    if provider == "ollama" and OLLAMA_URL:
        cmd += ["-u", OLLAMA_URL]

    # All commercial APIs need an API key. Add them to UNIX pass store.
    if provider != "ollama":
        cmd += ["-k", f"{provider}-api-key"]

    cmd += [ "-o", OPTIONS ]

    try:
        proc = subprocess.run(
            cmd,
            input=TEST_PROMPT.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"

    if proc.returncode != 0:
        return False, f"ERROR: {proc.stderr.decode().strip()}"

    output = proc.stdout.decode().strip()
    return True, output


# ----------------------------
# Main test logic
# ----------------------------

def main():
    if not shutil.which(COMPLETE):
        print(f"ERROR: cannot find {COMPLETE}")
        sys.exit(1)

    # ----------------------------
    # Command line argument parsing
    # ----------------------------
    # Usage:
    #   ./test.py
    #   ./test.py openai
    #   ./test.py openai gpt-4.1

    provider_filter = None
    model_filter = None

    if len(sys.argv) >= 2:
        provider_filter = sys.argv[1]

        if provider_filter not in MODELS:
            print(f"ERROR: Unknown provider '{provider_filter}'. Valid: {list(MODELS.keys())}")
            sys.exit(1)

    if len(sys.argv) >= 3:
        model_filter = sys.argv[2]

        if model_filter not in MODELS.get(provider_filter, []):
            print(f"ERROR: Unknown model '{model_filter}' for provider '{provider_filter}'.")
            print(f"Valid models: {MODELS[provider_filter]}")
            sys.exit(1)

    print("=== LLM Completion Test ===")
    print(f"Prompt:      {TEST_PROMPT}")
    print(f"Expecting:   {EXPECTED}\n")

    for provider, model_list in MODELS.items():

        # Apply provider filter
        if provider_filter and provider != provider_filter:
            continue

        print(f"\n=== Provider: {provider} ===")

        for model in model_list:

            # Apply model filter
            if model_filter and model != model_filter:
                continue

            print(f"\nModel: {model}")

            ok, output = run_completion(provider, model)

            if not ok:
                print(f"[FAIL] {output}")
                print("-" * 50)
                continue

            # Check expected result
            if EXPECTED in output:
                print("[PASS]")
            else:
                print("[FAIL] Output does not contain expected result.")
                print("Output was:")
                print(output)

            print("-" * 50)

    print("\nAll tests completed.\n")


if __name__ == "__main__":
    main()
