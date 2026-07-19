"""OCR 工作进程 — PaddleOCR 批量处理抽卡记录区域"""
import sys
import json
import os
import cv2

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"


def ocr_regions(image_path: str, regions_json: str) -> list:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
    img = cv2.imread(image_path)
    if img is None:
        return []

    regions = json.loads(regions_json)  # [[y1,y2], [y1,y2], ...]
    all_results = []
    for y1, y2 in regions:
        region = img[y1:y2, :]
        raw = ocr.ocr(region, cls=False)
        if raw[0] is None:
            all_results.append([])
            continue
        parsed = []
        for line in raw[0]:
            box = line[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            text, conf = line[1]
            parsed.append({
                "text": text,
                "confidence": float(conf),
                "box": [[int(p[0]), int(p[1])] for p in box],
            })
        all_results.append(parsed)
    return all_results


if __name__ == "__main__":
    image_path = sys.argv[1]
    regions_json = sys.argv[2]
    output_path = sys.argv[3]
    try:
        results = ocr_regions(image_path, regions_json)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False)
        print("OK")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
