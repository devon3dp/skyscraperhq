"""
ggml_whisper.py — load a whisper.cpp GGML model (ggml-*.bin) into a HuggingFace
transformers WhisperForConditionalGeneration and transcribe. Offline, no downloads.

Built because the box is airgapped: the only whisper weights present are the GGML
tiny.en file, and the whisper.cpp binary's shared libs were wiped. transformers +
torch(cu128) ARE installed, so we re-home the GGML weights into transformers.
"""
from __future__ import annotations
import struct, sys, time, wave
from functools import lru_cache
import numpy as np
import torch
from transformers import WhisperConfig, WhisperForConditionalGeneration, WhisperFeatureExtractor

# ---- special token ids for an english-only (.en) whisper tokenizer, n_vocab=51864
#   base gpt2 vocab: 0..50256 (50256 = <|endoftext|> = eot)
#   specials: sot=50257, langs 50258..50356 (99), translate=50357, transcribe=50358,
#             startoflm=50359, startofprev=50360, nospeech=50361, notimestamps=50362,
#             timestamps begin 50363
EOT = 50256
SOT = 50257
TRANSCRIBE = 50358
NOTIMESTAMPS = 50362
TS_BEGIN = 50363


@lru_cache(maxsize=1)
def _byte_decoder():
    # GPT-2 bytes<->unicode, inverted for decoding token strings back to raw bytes
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("\xa1"), ord("\xac") + 1)) + \
         list(range(ord("\xae"), ord("\xff") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


def load_ggml(path):
    f = open(path, "rb")
    magic = struct.unpack("<I", f.read(4))[0]
    assert magic == 0x67676d6c, f"bad magic {magic:#x}"
    (n_vocab, n_audio_ctx, n_audio_state, n_audio_head, n_audio_layer,
     n_text_ctx, n_text_state, n_text_head, n_text_layer, n_mels, ftype) = \
        struct.unpack("<11i", f.read(44))
    n_mel, n_fft = struct.unpack("<2i", f.read(8))
    f.seek(n_mel * n_fft * 4, 1)  # skip mel filters (we use HF feature extractor)
    n_tok = struct.unpack("<i", f.read(4))[0]
    vocab = []
    for _ in range(n_tok):
        l = struct.unpack("<I", f.read(4))[0]
        vocab.append(f.read(l))
    tensors = {}
    while True:
        b = f.read(12)
        if len(b) < 12:
            break
        ndim, nlen, tftype = struct.unpack("<3i", b)
        dims = struct.unpack("<%di" % ndim, f.read(4 * ndim))
        name = f.read(nlen).decode("utf-8")
        n = 1
        for d in dims:
            n *= d
        dt = np.float16 if tftype == 1 else np.float32
        data = np.frombuffer(f.read(n * dt().itemsize), dtype=dt)
        # ggml stores dims reversed vs numpy; reshape to reversed dims
        tensors[name] = data.reshape(tuple(reversed(dims))).astype(np.float32)
    f.close()
    hp = dict(n_vocab=n_vocab, n_audio_ctx=n_audio_ctx, n_audio_state=n_audio_state,
              n_audio_head=n_audio_head, n_audio_layer=n_audio_layer,
              n_text_ctx=n_text_ctx, n_text_state=n_text_state, n_text_head=n_text_head,
              n_text_layer=n_text_layer, n_mels=n_mels)
    return hp, vocab, tensors


def build_state_dict(hp, tensors):
    sd = {}
    t = lambda n: torch.from_numpy(tensors[n])
    # encoder
    sd["model.encoder.conv1.weight"] = t("encoder.conv1.weight")
    sd["model.encoder.conv1.bias"] = t("encoder.conv1.bias").reshape(-1)
    sd["model.encoder.conv2.weight"] = t("encoder.conv2.weight")
    sd["model.encoder.conv2.bias"] = t("encoder.conv2.bias").reshape(-1)
    sd["model.encoder.embed_positions.weight"] = t("encoder.positional_embedding")
    for i in range(hp["n_audio_layer"]):
        p = f"encoder.blocks.{i}."
        h = f"model.encoder.layers.{i}."
        sd[h + "self_attn.q_proj.weight"] = t(p + "attn.query.weight")
        sd[h + "self_attn.q_proj.bias"] = t(p + "attn.query.bias")
        sd[h + "self_attn.k_proj.weight"] = t(p + "attn.key.weight")  # no bias
        sd[h + "self_attn.v_proj.weight"] = t(p + "attn.value.weight")
        sd[h + "self_attn.v_proj.bias"] = t(p + "attn.value.bias")
        sd[h + "self_attn.out_proj.weight"] = t(p + "attn.out.weight")
        sd[h + "self_attn.out_proj.bias"] = t(p + "attn.out.bias")
        sd[h + "self_attn_layer_norm.weight"] = t(p + "attn_ln.weight")
        sd[h + "self_attn_layer_norm.bias"] = t(p + "attn_ln.bias")
        sd[h + "fc1.weight"] = t(p + "mlp.0.weight")
        sd[h + "fc1.bias"] = t(p + "mlp.0.bias")
        sd[h + "fc2.weight"] = t(p + "mlp.2.weight")
        sd[h + "fc2.bias"] = t(p + "mlp.2.bias")
        sd[h + "final_layer_norm.weight"] = t(p + "mlp_ln.weight")
        sd[h + "final_layer_norm.bias"] = t(p + "mlp_ln.bias")
    sd["model.encoder.layer_norm.weight"] = t("encoder.ln_post.weight")
    sd["model.encoder.layer_norm.bias"] = t("encoder.ln_post.bias")
    # decoder
    sd["model.decoder.embed_tokens.weight"] = t("decoder.token_embedding.weight")
    sd["model.decoder.embed_positions.weight"] = t("decoder.positional_embedding")
    for i in range(hp["n_text_layer"]):
        p = f"decoder.blocks.{i}."
        h = f"model.decoder.layers.{i}."
        sd[h + "self_attn.q_proj.weight"] = t(p + "attn.query.weight")
        sd[h + "self_attn.q_proj.bias"] = t(p + "attn.query.bias")
        sd[h + "self_attn.k_proj.weight"] = t(p + "attn.key.weight")
        sd[h + "self_attn.v_proj.weight"] = t(p + "attn.value.weight")
        sd[h + "self_attn.v_proj.bias"] = t(p + "attn.value.bias")
        sd[h + "self_attn.out_proj.weight"] = t(p + "attn.out.weight")
        sd[h + "self_attn.out_proj.bias"] = t(p + "attn.out.bias")
        sd[h + "self_attn_layer_norm.weight"] = t(p + "attn_ln.weight")
        sd[h + "self_attn_layer_norm.bias"] = t(p + "attn_ln.bias")
        sd[h + "encoder_attn.q_proj.weight"] = t(p + "cross_attn.query.weight")
        sd[h + "encoder_attn.q_proj.bias"] = t(p + "cross_attn.query.bias")
        sd[h + "encoder_attn.k_proj.weight"] = t(p + "cross_attn.key.weight")
        sd[h + "encoder_attn.v_proj.weight"] = t(p + "cross_attn.value.weight")
        sd[h + "encoder_attn.v_proj.bias"] = t(p + "cross_attn.value.bias")
        sd[h + "encoder_attn.out_proj.weight"] = t(p + "cross_attn.out.weight")
        sd[h + "encoder_attn.out_proj.bias"] = t(p + "cross_attn.out.bias")
        sd[h + "encoder_attn_layer_norm.weight"] = t(p + "cross_attn_ln.weight")
        sd[h + "encoder_attn_layer_norm.bias"] = t(p + "cross_attn_ln.bias")
        sd[h + "fc1.weight"] = t(p + "mlp.0.weight")
        sd[h + "fc1.bias"] = t(p + "mlp.0.bias")
        sd[h + "fc2.weight"] = t(p + "mlp.2.weight")
        sd[h + "fc2.bias"] = t(p + "mlp.2.bias")
        sd[h + "final_layer_norm.weight"] = t(p + "mlp_ln.weight")
        sd[h + "final_layer_norm.bias"] = t(p + "mlp_ln.bias")
    sd["model.decoder.layer_norm.weight"] = t("decoder.ln.weight")
    sd["model.decoder.layer_norm.bias"] = t("decoder.ln.bias")
    sd["proj_out.weight"] = t("decoder.token_embedding.weight")  # tied
    return sd


class GgmlWhisper:
    def __init__(self, path, device=None):
        self.hp, self.vocab, tensors = load_ggml(path)
        cfg = WhisperConfig(
            vocab_size=self.hp["n_vocab"], num_mel_bins=self.hp["n_mels"],
            d_model=self.hp["n_audio_state"],
            encoder_layers=self.hp["n_audio_layer"], encoder_attention_heads=self.hp["n_audio_head"],
            decoder_layers=self.hp["n_text_layer"], decoder_attention_heads=self.hp["n_text_head"],
            encoder_ffn_dim=self.hp["n_audio_state"] * 4, decoder_ffn_dim=self.hp["n_text_state"] * 4,
            max_source_positions=self.hp["n_audio_ctx"], max_target_positions=self.hp["n_text_ctx"],
            activation_function="gelu", scale_embedding=False,
            bos_token_id=SOT, eos_token_id=EOT, pad_token_id=EOT, decoder_start_token_id=SOT,
        )
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        m = WhisperForConditionalGeneration(cfg)
        missing, unexpected = m.load_state_dict(build_state_dict(self.hp, tensors), strict=False)
        # only proj_out (tied) may show; assert nothing important missing
        real_missing = [k for k in missing if "proj_out" not in k]
        assert not real_missing, f"missing weights: {real_missing[:8]}"
        assert not unexpected, f"unexpected: {unexpected[:8]}"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.model = m.to(self.device).to(self.dtype).eval()
        self.fe = WhisperFeatureExtractor(feature_size=self.hp["n_mels"], sampling_rate=16000,
                                          hop_length=160, chunk_length=30, n_fft=400)
        self.bd = _byte_decoder()

    def _decode_tokens(self, ids):
        chars = "".join(self.vocab[i].decode("utf-8", "replace") if False else
                        self.vocab[i].decode("latin-1") for i in ids if i < len(self.vocab))
        try:
            return bytearray(self.bd[c] for c in chars).decode("utf-8", "replace")
        except KeyError:
            return "".join(self.vocab[i].decode("utf-8", "replace") for i in ids)

    @torch.inference_mode()
    def transcribe(self, audio_f32, prefix=(SOT, NOTIMESTAMPS), max_new=224):
        feats = self.fe(audio_f32, sampling_rate=16000, return_tensors="pt").input_features
        feats = feats.to(self.device).to(self.dtype)
        enc = self.model.model.encoder(feats).last_hidden_state
        ids = list(prefix)
        for _ in range(max_new):
            di = torch.tensor([ids], device=self.device)
            logits = self.model(decoder_input_ids=di, encoder_outputs=(enc,)).logits[0, -1]
            nxt = int(logits.argmax())
            if nxt == EOT:
                break
            ids.append(nxt)
        out = [i for i in ids[len(prefix):] if i < TS_BEGIN and i != EOT and i < len(self.vocab)]
        return self._decode_tokens(out).strip()


def read_wav_16k_mono(path):
    w = wave.open(path, "rb")
    sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    raw = w.readframes(w.getnframes())
    w.close()
    assert sw == 2, f"expected 16-bit wav, got sampwidth {sw}"
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    assert sr == 16000, f"expected 16kHz, got {sr}"
    return a


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/vaults/nvme0/qsb_tower_v1/data/whisper/ggml-tiny.en.bin"
    t0 = time.time()
    m = GgmlWhisper("/vaults/nvme0/qsb_tower_v1/data/whisper/ggml-tiny.en.bin")
    print(f"[load {time.time()-t0:.2f}s device={m.device}]")
    for wav in sys.argv[1:]:
        audio = read_wav_16k_mono(wav)
        t1 = time.time()
        txt = m.transcribe(audio)
        dur = len(audio) / 16000
        print(f"[{wav}] audio={dur:.2f}s transcribe={time.time()-t1:.2f}s")
        print("   =>", repr(txt))
