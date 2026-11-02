from __future__ import annotations

# {
#   責務: [OllamaPromptCorrector: Ollama API経由のmodel discovery and prompt correctionを提供する]
#   処理: [API payloadを構築し、HTTP responseを検証してpromptを返す]
#   フィールド: [INSTRUCTION and stateless API request operations]
# }
class OllamaPromptCorrector:
    """Ollama APIで自由文を画像生成向けタグへ整形する。"""
    INSTRUCTION = "Convert the user's request into a concise comma-separated image generation prompt. Keep useful English tags, translate Japanese concepts into common English image tags, and output only the prompt without explanation."

    # {
    #   責務: [models: Ollama instanceが利用可能なmodel namesを取得する]
    #   処理: [GET /api/tagsを呼び、HTTP errorsをraiseして空名を除去する]
    #   引数: [api_url, requests_module]
    #   戻り値: [list[str]]
    # }
    def models(self, api_url: str, requests_module) -> list[str]:
        response=requests_module.get(api_url.rstrip("/")+"/api/tags",timeout=10); response.raise_for_status()
        return [str(item.get("name","")).strip() for item in response.json().get("models",[]) if str(item.get("name","")).strip()]

    # {
    #   責務: [payload: modelとsource textからgeneration request payloadを作る]
    #   処理: [instruction, user request, and non-streaming temperature optionsをformatする]
    #   引数: [model, source]
    #   戻り値: [dict]
    # }
    def payload(self, model: str, source: str) -> dict:
        return {"model":model,"prompt":f"{self.INSTRUCTION}\n\nUser request:\n{source.strip()}","stream":False,"options":{"temperature":0.2}}

    # {
    #   責務: [correct: 自由文をOllamaで画像生成向けpromptへ変換する]
    #   処理: [入力をvalidateし、generation APIを呼び、empty responseを拒否する]
    #   引数: [api_url, model, source, requests_module]
    #   戻り値: [str]
    # }
    def correct(self, api_url: str, model: str, source: str, requests_module) -> str:
        if not source.strip(): raise ValueError("校正するプロンプトを入力してください")
        if not model.strip(): raise ValueError("Ollamaモデルを指定してください")
        response=requests_module.post(api_url.rstrip("/")+"/api/generate",json=self.payload(model,source),timeout=180); response.raise_for_status()
        result=str(response.json().get("response","")).strip()
        if not result: raise RuntimeError("Ollamaからプロンプトを取得できませんでした")
        return result
