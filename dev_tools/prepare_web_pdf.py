"""部署时预热 OCR 模型及配套字体；只下载公开 OCR 资产，不读取密钥或数据库。"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from rapidocr import RapidOCR


def main():
    image = Image.new("RGB", (1000, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 30), "Course Agent OCR readiness 123456789", fill="black", font=ImageFont.load_default(size=32))
    result = RapidOCR(params={"EngineConfig.onnxruntime.intra_op_num_threads": 2,
                              "EngineConfig.onnxruntime.inter_op_num_threads": 1})(np.asarray(image))
    if not result.txts:
        raise RuntimeError("OCR 预热未识别到测试文字，请检查依赖与模型。")
    print("[ok] PDF/OCR 本地模型与字体已准备；正式读取不再临时下载模型。")


if __name__ == "__main__":
    main()
