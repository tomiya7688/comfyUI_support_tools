"""Single source of truth for legacy tool identity, presentation, and bindings."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any


# {
#   責務: [ToolDescriptor: legacy toolのstable IDとUI/settings/migration bindingを保持する]
#   フィールド: [id、label、category、settings ID、implementation、legacy class、capability/action metadata]
# }
@dataclass(frozen=True)
class ToolDescriptor:
    id: str
    label: str
    category: str
    settings_id: str
    implementation: str
    legacy_class: str | None = None
    media_kinds: tuple[str, ...] = ()
    action_id: str | None = None
    availability: str = "available"
    migration_state: str = "legacy"


# {
#   責務: [ToolRegistry: descriptor IDs/settings IDsを一意検証しlegacy UI metadataを解決する]
#   フィールド: [ordered descriptorsとID/class lookup]
# }
class ToolRegistry:
    # {
    #   責務: [__init__: descriptor tupleを検証してregistry snapshotを作る]
    #   処理: [1: duplicate ID/settings ID/legacy classを検出する 2: stable orderを保持する]
    #   引数: [descriptors: ordered tool descriptors]
    #   戻り値: []
    # }
    def __init__(self, descriptors: tuple[ToolDescriptor, ...]):
        ids = [item.id for item in descriptors]
        settings_ids = [item.settings_id for item in descriptors]
        legacy_classes = [item.legacy_class for item in descriptors if item.legacy_class]
        if len(ids) != len(set(ids)):
            raise ValueError("tool descriptor IDs must be unique")
        if len(settings_ids) != len(set(settings_ids)):
            raise ValueError("tool settings IDs must be unique")
        if len(legacy_classes) != len(set(legacy_classes)):
            raise ValueError("legacy class names must be unique")
        for item in descriptors:
            if not all(
                (
                    item.id.strip(),
                    item.label.strip(),
                    item.category.strip(),
                    item.settings_id.strip(),
                    item.implementation.strip(),
                )
            ):
                raise ValueError("tool descriptor identity fields must be non-empty")
            if ":" not in item.implementation:
                raise ValueError("tool implementation must use module:attribute notation")
        self.descriptors = descriptors
        self._by_legacy_class = {
            item.legacy_class: item for item in descriptors if item.legacy_class
        }

    # {
    #   責務: [settings_id_for_legacy_class: old tab class nameからmigration settings IDを得る]
    #   処理: [1: class-name adapter mappingを検索する 2: unknown classをNoneで返す]
    #   引数: [class_name: legacy Python class name]
    #   戻り値: [stable settings ID or None]
    # }
    def settings_id_for_legacy_class(self, class_name: str) -> str | None:
        descriptor = self._by_legacy_class.get(class_name)
        return descriptor.settings_id if descriptor else None

    # {
    #   責務: [load_implementation: component bindingを遅延importして返す]
    #   処理: [1: module/attributeを分割する 2: classをimportする 3: callableを返す]
    #   引数: [descriptor: registered tool]
    #   戻り値: [legacy component class/factory]
    # }
    @staticmethod
    def load_implementation(descriptor: ToolDescriptor) -> Any:
        module_name, attribute = descriptor.implementation.split(":", maxsplit=1)
        module = import_module(module_name)
        implementation = getattr(module, attribute)
        if not callable(implementation):
            raise TypeError(f"tool implementation is not callable: {descriptor.id}")
        return implementation


# {
#   責務: [TOOL_REGISTRY: actual legacy UI bindingとstable tool/settings metadataを集約する]
#   フィールド: [single ordered descriptor source for tab shell/catalog/settings migration]
# }
TOOL_REGISTRY = ToolRegistry(
    (
        ToolDescriptor(
            "start_backend",
            "{backend}起動",
            "生成",
            "application.start_backend",
            "scripts.tabs.start_webui:StartWebUITab",
            "StartWebUITab",
        ),
        ToolDescriptor(
            "random_image",
            "random txt2img",
            "生成",
            "generation.random_image",
            "scripts.tabs.random_image:RandomImageTab",
            "RandomImageTab",
        ),
        ToolDescriptor(
            "prompt_generate",
            "Prompt生成",
            "生成",
            "generation.prompt_generate",
            "scripts.tabs.prompt_generate:PromptGenerateTab",
            "PromptGenerateTab",
        ),
        ToolDescriptor(
            "random_img2img",
            "Random img2img",
            "生成",
            "generation.random_img2img",
            "scripts.tabs.random_img2img:RandomImg2ImgTab",
            "RandomImg2ImgTab",
        ),
        ToolDescriptor(
            "folder_tagger",
            "Folder Tagger",
            "Prompt・Tag",
            "tagger.folder",
            "scripts.tabs.folder_tagger:FolderTaggerTab",
            "FolderTaggerTab",
        ),
        ToolDescriptor(
            "ai_image_cluster",
            "AI画像クラスタ",
            "Image・Video",
            "image.ai_cluster",
            "scripts.tabs.ai_image_cluster:AIImageClusterTab",
            "AIImageClusterTab",
        ),
        ToolDescriptor(
            "random_line_picker",
            "Random Line Picker",
            "Prompt・Tag",
            "text.random_line_picker",
            "scripts.tabs.random_line_picker:RandomLinePickerTab",
            "RandomLinePickerTab",
        ),
        ToolDescriptor(
            "body_prompt",
            "Body Prompt",
            "Prompt・Tag",
            "prompt.body",
            "scripts.tabs.body_prompt:BodyPromptTab",
            "BodyPromptTab",
        ),
        ToolDescriptor(
            "tag_delete",
            "Tag Deleter",
            "Prompt・Tag",
            "tagger.delete",
            "scripts.tabs.tag_deleter:TagDeleterTab",
            "TagDeleterTab",
        ),
        ToolDescriptor(
            "tag_split",
            "Tag Splitter",
            "Prompt・Tag",
            "tagger.split",
            "scripts.tabs.tag_splitter:TagSplitterTab",
            "TagSplitterTab",
        ),
        ToolDescriptor(
            "tag_replace",
            "Tag Replacer",
            "Prompt・Tag",
            "tagger.replace",
            "scripts.tabs.tag_replacer:TagReplacerTab",
            "TagReplacerTab",
        ),
        ToolDescriptor(
            "tag_to_prompt",
            "Tag to Prompt",
            "Prompt・Tag",
            "tagger.to_prompt",
            "scripts.tabs.tag_to_prompt:TagToPromptTab",
            "TagToPromptTab",
        ),
        ToolDescriptor(
            "flat_copy",
            "Flat Copy/Move",
            "Utility",
            "files.flat_copy",
            "scripts.tabs.flat_file_copy:FlatFileCopyTab",
            "FlatFileCopyTab",
        ),
        ToolDescriptor(
            "text_merge",
            "Text Merger",
            "Utility",
            "text.merge",
            "scripts.tabs.text_merger:TextMergerTab",
            "TextMergerTab",
        ),
        ToolDescriptor(
            "video_extract_frames",
            "Movie Frames",
            "Image・Video",
            "video.extract_frames",
            "scripts.tabs.screenshot_from_movie:ScreenshotFromMovieTab",
            "ScreenshotFromMovieTab",
            ("video",),
        ),
        ToolDescriptor(
            "character_library",
            "Character Library",
            "Character",
            "character.library",
            "scripts.tabs.character_library:CharacterLibraryPanel",
            "CharacterLibraryPanel",
            ("image",),
        ),
        ToolDescriptor(
            "movie_to_text",
            "Movie to Text",
            "Image・Video",
            "video.to_text",
            "scripts.tabs.movie_to_text:MovieToTextTab",
            "MovieToTextTab",
            ("video",),
        ),
        ToolDescriptor(
            "convert_webp",
            "画像をWEBP変換",
            "Image・Video",
            "image.convert_webp",
            "scripts.tabs.images_to_webp:ImagesToWebpTab",
            "ImagesToWebpTab",
            ("image",),
        ),
        ToolDescriptor(
            "delete_duplicate_lines",
            "重複行削除",
            "Utility",
            "text.remove_duplicate_lines",
            "scripts.tabs.duplicate_line_delete:DuplicateLineDeleteTab",
            "DuplicateLineDeleteTab",
        ),
        ToolDescriptor(
            "video_repair",
            "ffmpeg修復",
            "Image・Video",
            "video.repair",
            "scripts.tabs.ffmpeg_repair:FfmpegRepairTab",
            "FfmpegRepairTab",
            ("video",),
        ),
        ToolDescriptor(
            "check_braces",
            "Brace Check",
            "Prompt・Tag",
            "developer.check_braces",
            "scripts.tabs.check_braces:CheckBracesTab",
            "CheckBracesTab",
        ),
        ToolDescriptor(
            "wildcard_check",
            "Wildcard Check",
            "Prompt・Tag",
            "wildcard.check",
            "scripts.tabs.wildcard_checker:WildcardCheckerTab",
            "WildcardCheckerTab",
        ),
        ToolDescriptor(
            "wildcard_move",
            "Wildcard Move",
            "Prompt・Tag",
            "wildcard.move",
            "scripts.tabs.wildcard_move:WildcardMoveTab",
            "WildcardMoveTab",
        ),
        ToolDescriptor(
            "archive_zip",
            "Zipper",
            "Utility",
            "archive.zip",
            "scripts.tabs.zipper:ZipperTab",
            "ZipperTab",
        ),
        ToolDescriptor(
            "youtube_download",
            "YouTube Downloader",
            "Image・Video",
            "video.youtube_download",
            "scripts.tabs.youtube_downloader:YouTubeDownloaderTab",
            "YouTubeDownloaderTab",
            ("video",),
        ),
        ToolDescriptor(
            "video_reencode",
            "Video Reencoder",
            "Image・Video",
            "video.reencode",
            "scripts.tabs.video_reencoder:VideoReencoderTab",
            "VideoReencoderTab",
            ("video",),
        ),
        ToolDescriptor(
            "static_spec",
            "静的仕様書",
            "Development",
            "developer.static_spec",
            "scripts.tabs.static_spec:StaticSpecTab",
            "StaticSpecTab",
        ),
        ToolDescriptor(
            "docstring_audit",
            "Docstring検査",
            "Development",
            "developer.docstring_audit",
            "scripts.tabs.docstring_audit:DocstringAuditTab",
            "DocstringAuditTab",
        ),
        ToolDescriptor(
            "dependency_status",
            "依存状態",
            "Development",
            "developer.dependency_status",
            "scripts.tabs.dependency_status:DependencyStatusTab",
            "DependencyStatusTab",
        ),
        ToolDescriptor(
            "ollama_prompt",
            "Ollama Prompt",
            "AI",
            "prompt.ollama",
            "scripts.tabs.ollama_prompt:OllamaPromptTab",
            "OllamaPromptTab",
        ),
        ToolDescriptor(
            "touka_enhancer",
            "半透明素材強調",
            "Image・Video",
            "image.touka_enhancer",
            "scripts.tabs.touka_enhancer:ToukaEnhancerTab",
            "ToukaEnhancerTab",
            ("image",),
        ),
        ToolDescriptor(
            "touka_evaluation_report",
            "Touka評価履歴",
            "Image・Video",
            "image.touka_evaluation_report",
            "scripts.tabs.touka_evaluation_report:ToukaEvaluationReportTab",
            "ToukaEvaluationReportTab",
            ("image",),
        ),
    )
)
