import { defineAgent } from "eve";
import { openai } from "eve/models/openai";

// openai() llama directo a OpenAI y lee OPENAI_API_KEY.
// Alternativa: un string de AI Gateway, por ejemplo model: "openai/gpt-6-luna".
export default defineAgent({
  model: openai("gpt-6-luna"),
});
