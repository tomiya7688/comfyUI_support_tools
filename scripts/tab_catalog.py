"""Legacy UI migration metadata only. Keep order synchronized with app.py.

The shell receives metadata, never legacy widget classes. The parity test prevents
opening a different tab after the legacy UI changes its order.
"""
# Stable class-name ID, display label, category; no imports or process startup.
TAB_CATALOG = (
    ("StartWebUITab", "Backend起動", "生成"),
    ("RandomImageTab", "random txt2img", "生成"),
    ("PromptGenerateTab", "Prompt生成", "生成"),
    ("RandomImg2ImgTab", "Random img2img", "生成"),
    ("FolderTaggerTab", "Folder Tagger", "Prompt・Tag"),
    ("RandomLinePickerTab", "Random Line Picker", "Prompt・Tag"),
    ("BodyPromptTab", "Body Prompt", "Prompt・Tag"),
    ("TagDeleterTab", "Tag Deleter", "Prompt・Tag"),
    ("TagSplitterTab", "Tag Splitter", "Prompt・Tag"),
    ("TagReplacerTab", "Tag Replacer", "Prompt・Tag"),
    ("TagToPromptTab", "Tag to Prompt", "Prompt・Tag"),
    ("FlatFileCopyTab", "Flat Copy/Move", "Utility"),
    ("TextMergerTab", "Text Merger", "Utility"),
    ("ScreenshotFromMovieTab", "Movie Frames", "Image・Video"),
    ("MovieToTextTab", "Movie to Text", "Image・Video"),
    ("ImagesToWebpTab", "画像をWEBP変換", "Image・Video"),
    ("DuplicateLineDeleteTab", "重複行削除", "Utility"),
    ("FfmpegRepairTab", "ffmpeg修復", "Image・Video"),
    ("CheckBracesTab", "Brace Check", "Prompt・Tag"),
    ("WildcardCheckerTab", "Wildcard Check", "Prompt・Tag"),
    ("WildcardMoveTab", "Wildcard Move", "Prompt・Tag"),
    ("ZipperTab", "Zipper", "Utility"),
    ("YouTubeDownloaderTab", "YouTube Downloader", "Image・Video"),
    ("VideoReencoderTab", "Video Reencoder", "Image・Video"),
    ("StaticSpecTab", "静的仕様書", "Development"),
    ("DocstringAuditTab", "Docstring検査", "Development"),
    ("DependencyStatusTab", "依存状態", "Development"),
    ("OllamaPromptTab", "Ollama Prompt", "AI"),
    ("ToukaEnhancerTab", "半透明素材強調", "Image・Video"),
    ("ToukaEvaluationReportTab", "Touka評価履歴", "Image・Video"),
)


def tab_index(tool_id: str) -> int:
    for index, (identifier, _label, _category) in enumerate(TAB_CATALOG):
        if identifier == tool_id:
            return index
    raise ValueError(f"Unknown legacy tool: {tool_id}")
