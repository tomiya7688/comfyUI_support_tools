from __future__ import annotations

class OllamaPromptCorrector:
    """Ollama APIで自由文を画像生成向けタグへ整形する。"""
    INSTRUCTION = "Convert the user's request into a concise comma-separated image generation prompt. Keep useful English tags, translate Japanese concepts into common English image tags, and output only the prompt without explanation."
    def models(self, api_url: str, requests_module) -> list[str]:
        response=requests_module.get(api_url.rstrip("/")+"/api/tags",timeout=10); response.raise_for_status()
        return [str(item.get("name","")).strip() for item in response.json().get("models",[]) if str(item.get("name","")).strip()]
    def payload(self, model: str, source: str) -> dict:
        return {"model":model,"prompt":f"{self.INSTRUCTION}\n\nUser request:\n{source.strip()}","stream":False,"options":{"temperature":0.2}}
    def correct(self, api_url: str, model: str, source: str, requests_module) -> str:
        if not source.strip(): raise ValueError("校正するプロンプトを入力してください")
        if not model.strip(): raise ValueError("Ollamaモデルを指定してください")
        response=requests_module.post(api_url.rstrip("/")+"/api/generate",json=self.payload(model,source),timeout=180); response.raise_for_status()
        result=str(response.json().get("response","")).strip()
        if not result: raise RuntimeError("Ollamaからプロンプトを取得できませんでした")
        return result
