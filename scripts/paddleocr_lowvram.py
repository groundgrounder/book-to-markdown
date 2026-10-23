#!/usr/bin/env python3
"""paddleocr CLI 包装：PaddleOCR-VL 权重先读进内存，再拷进 GPU 上的模型。

两处改动（实测 6GB 卡：原版加载峰值 >5.6GB 必 OOM；改后模型 1.8GB、加载峰值 3.7GB）：
1. 原版 load_state_dict 把整份权重直接拷进显存再做 dtype 转换 → 改为先读进内存。
2. 原版把视觉编码器（visual/mlp_AR）强制留在 fp32（1.7GB）→ 改为全模型 bf16。
   checkpoint 本身就是 bf16 发布的（config.json torch_dtype=bfloat16），vLLM 等服务端后端也是整模 bf16 跑。
用法与 paddleocr 完全相同：paddleocr_lowvram.py doc_parser -i ... --save_path ...
"""
import faulthandler
import os
import signal
import sys

# 卡死排查：kill -USR1 <pid> 把所有线程的 Python 调用栈打到 stderr（pdf_ocr.sh 超时会先发 USR1 再杀）
faulthandler.register(signal.SIGUSR1, all_threads=True)
if os.environ.get("B2M_DEBUG_VL"):
    faulthandler.dump_traceback_later(60, repeat=True)   # 每分钟打一次栈：看生成是在走还是卡死

import paddle
from paddlex.inference.models.common.transformers.transformers import model_utils as _mu
from paddlex.inference.models.doc_vlm.modeling import PaddleOCRVLForConditionalGeneration

PaddleOCRVLForConditionalGeneration._keep_in_fp32_modules = None

_orig_load_state_dict = _mu.load_state_dict


def _load_state_dict_on_cpu(*args, **kwargs):
    dev = paddle.device.get_device()
    paddle.set_device("cpu")
    try:
        return _orig_load_state_dict(*args, **kwargs)
    finally:
        paddle.set_device(dev)


_mu.load_state_dict = _load_state_dict_on_cpu

# 心跳：每生成一个 token 都会调用一次 forward，至多每 3 秒刷新一次心跳文件的 mtime。
# pdf_ocr.sh 的看门狗据此区分"还在生成（密集索引页一批 8 页要 5 分钟以上）"和"真卡死"。
_HB = os.environ.get("B2M_HEARTBEAT")
if _HB:
    import time as _time

    open(_HB, "a").close()
    _orig_forward = PaddleOCRVLForConditionalGeneration.forward
    _last = [0.0]

    def _forward_with_heartbeat(self, *a, **k):
        now = _time.time()
        if now - _last[0] > 3:
            _last[0] = now
            try: os.utime(_HB, None)
            except OSError: pass
        return _orig_forward(self, *a, **k)

    PaddleOCRVLForConditionalGeneration.forward = _forward_with_heartbeat

if os.environ.get("B2M_DEBUG_VL"):
    # 每个版面块的生成耗时与输出长度打到 stderr，排查哪个块在失控生成
    import time
    from paddlex.inference.models.doc_vlm.predictor import DocVLMLocalPredictor as DocVLMPredictor

    _orig_process = DocVLMPredictor.process

    def _timed_process(self, data, *a, **k):
        t = time.time()
        out = _orig_process(self, data, *a, **k)
        s = str(out)
        print(f"[vl-block] {time.time() - t:.1f}s n={len(data)} len={len(s)} tail={s[-80:]!r}", file=sys.stderr, flush=True)
        return out

    DocVLMPredictor.process = _timed_process

from paddleocr.__main__ import console_entry  # noqa: E402

sys.exit(console_entry())
