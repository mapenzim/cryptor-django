(() => {
  const button = document.querySelector("#ai-generate");
  if (!button) return;

  const prompt = document.querySelector("#ai-prompt");
  const content = document.querySelector("#id_content");
  const status = document.querySelector("#ai-status");
  const csrf = document.querySelector("#document-form input[name='csrfmiddlewaretoken']");

  button.addEventListener("click", async () => {
    const instruction = prompt.value.trim();
    if (!instruction) {
      status.textContent = "Type an instruction first.";
      return;
    }
    if (content.value.trim() && !window.confirm("Replace the current editor content with generated text?")) {
      return;
    }

    button.disabled = true;
    button.textContent = "Generating…";
    status.textContent = "Ollama is working locally. Larger models can take a minute or two.";
    try {
      const response = await fetch("/api/ai/generate/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf.value,
        },
        body: JSON.stringify({prompt: instruction}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Generation failed.");
      content.value = result.content;
      status.textContent = "Generated text is ready. Save to encrypt it.";
      content.focus();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = "Generate with Ollama";
    }
  });
})();

