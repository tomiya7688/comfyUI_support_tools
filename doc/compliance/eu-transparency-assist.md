# EU AI Act Transparency Assist

EU Transparency Assist is an opt-in technical provenance aid. It does not determine
whether a user is legally in scope and does not guarantee compliance with the EU AI
Act or any other law. Ordinary exports remain unchanged unless the user explicitly
enables the option. The application never enables it from IP address, locale, or OS
language.

The Analysis export dialog can write an optional `.transparency.json` sidecar. It
records the asset hash, the fact that the export was a metadata operation, the
profile version and references, and the available operation history. Its source
classification is `unknown` because this inspector does not know how the image was
created. The dialog also lets the user explicitly set a technical classification,
disclosure levels, human oversight, and deepfake-disclosure context. A
classification selected in the dialog is recorded as a user override. Prompt,
model, and workflow disclosure default to `none`; the pre-existing
analysis JSON sidecar also redacts prompt and negative prompt when this mode is on.
The original image is never overwritten.

The enablement setting defaults to OFF. The user can save the current choice as a
global default or an Analysis-export-only override; the effective order is
per-export choice, application override, global default, then OFF. These
preferences contain no signing keys or prompts and are stored under the user's
configuration directory. No location-based auto-enable is performed.

For PNG, an optional second copy can carry a machine-readable PNG text chunk. The
copy is verified before it is written, existing text and common color/profile
metadata are retained, and the source pixels are not changed. Existing C2PA PNGs
are rejected by this path so Pillow cannot strip their credentials. JPEG, WebP,
audio, and video are not rewritten by this PNG metadata path; use a signed C2PA
adapter or sidecar for those formats.

The profile registry starts with `eu_ai_act_article50_2026` (profile version
`2026.1`). It is data-driven so later references and versions can be added without
changing the export contract. Classification supports `generated`, `ai_modified`,
`conventional_edit`, and `unknown`; the application does not make a legal
substantial-alteration determination. Deepfake assistance records explicit user
indications and is not an identity detector or legal classifier.

## C2PA signing and verification

C2PA support is optional. Install the pinned SDK in the application's environment
when needed:

```sh
python -m pip install -r requirements-transparency.txt
```

`shared.c2pa_adapter.C2paAdapter` uses the official C2PA SDK. It creates IPTC
`digitalSourceType` values through the SDK's builder intent API:

- AI generation: `trainedAlgorithmicMedia`
- AI-assisted edit: `compositeWithTrainedAlgorithmicMedia`
- conventional edit: `humanEdits`

For edits, the input is recorded as an ingredient. Existing C2PA manifests on that
input are preserved as ingredient provenance. `verify()` reports manifest presence,
assertion values, SDK validation state, cryptographic signature validation, and
certificate trust separately. A valid signature from an untrusted certificate is
not reported as verified. Strict verification is the default; a caller may select
the explicit warning policy, but the returned report remains unverified.

Signing is available only when both Transparency Assist and C2PA signing are
explicitly enabled. The adapter accepts a `SignerProvider`, allowing OS key-store,
KMS, HSM, or a user-managed secure PEM store. `PemFileSignerProvider` is a simple
adapter for PEM files selected outside project metadata; private key bytes are
never logged or included in sidecars. Do not place production keys in the checkout
or test fixtures. Production deployments should inject their organization-approved
secure signer and verification trust anchors through `C2paAdapter(context_factory=...)`.

The Analysis export dialog can create a signed C2PA copy after the user explicitly
selects a classification, certificate, and private-key file. The selected paths
are not persisted. A warning policy can retain a signed output when the SDK reports
an untrusted credential; the sidecar still records `verified: false`. The default
policy blocks that output. The ComfyUI and AUTOMATIC1111 sequence image-generation commands can create provenance sidecars, PNG metadata copies, or C2PA-signed copies when explicitly enabled and given an injected signer. The Analysis dialog can also sign image copies. This repository has no video-generation/exporter or retouch application, so MP4 signing is available through the shared adapter but requires explicit wiring by a host. Third-party services are not guaranteed to preserve metadata after export. Signing requires a valid certificate; signing without an organization-trusted certificate
can produce a cryptographically valid but untrusted credential, which is exposed
as such in the verification report.

## References

- Regulation (EU) 2024/1689, Article 50
- [European Commission Article 50 FAQ](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)
- [C2PA Technical Specification 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html)
