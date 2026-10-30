import { DefaultSandbox, defineSandbox } from "eve/sandbox";

// Los archivos de agent/sandbox/workspace/ se copian a /workspace en cada sesión nueva.
// En `eve dev` sin Docker, eve usa just-bash: un shell en JavaScript, sin binarios nativos.
export const environment = DefaultSandbox.environment();
export default defineSandbox(() => environment.open());
