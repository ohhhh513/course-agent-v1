#!/usr/bin/env python
"""
把本地 resources/（covers / data-structures-1-9 / uploads）批量上传到 Cloudflare R2 桶。

用法（PowerShell）：
  $env:R2_ACCOUNT_ID="<你的账号ID>"
  $env:R2_ACCESS_KEY="<你的AccessKey>"
  $env:R2_SECRET_KEY="<你的SecretKey>"
  $env:R2_BUCKET="course-agent-resources"   # 可省略，默认 course-agent-resources
  python3.11 backend\\upload_resources_to_r2.py

说明：
  - 依赖 boto3（pip install boto3）
  - 保持 resources/ 目录结构上传（桶根 = resources/ 根）
  - 幂等：已存在且大小一致的文件自动跳过，支持断点续传
  - 大文件由 boto3 的 upload_file 自动做分片（multipart）
"""
import os
import sys
from pathlib import Path

import boto3


def main() -> int:
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    access_key = os.getenv("R2_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID", "")
    secret_key = os.getenv("R2_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY", "")
    bucket = os.getenv("R2_BUCKET", "course-agent-resources").strip()

    if not (account_id and access_key and secret_key):
        print("[error] 请设置环境变量 R2_ACCOUNT_ID / R2_ACCESS_KEY / R2_SECRET_KEY")
        return 1

    # 项目根：本脚本位于 backend/ 下，向上两级为项目根
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "resources"
    if not src_dir.is_dir():
        print(f"[error] 找不到资源目录：{src_dir}")
        return 1

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    files = [p for p in src_dir.rglob("*") if p.is_file()]
    if not files:
        print("[error] resources/ 下没有文件")
        return 1

    uploaded = skipped = failed = 0
    total = len(files)
    print(f"[r2] 桶={bucket} 共 {total} 个文件，源目录={src_dir}")
    for i, path in enumerate(files, 1):
        key = path.relative_to(src_dir).as_posix()  # 保持相对目录结构，使用正斜杠
        local_size = path.stat().st_size
        # 幂等：已存在且大小一致则跳过
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            if head.get("ContentLength") == local_size:
                skipped += 1
                continue
        except Exception:
            pass  # 不存在则上传
        try:
            s3.upload_file(Bucket=bucket, Key=key, Filename=str(path))
            uploaded += 1
        except Exception as e:
            failed += 1
            print(f"  [x] {key}: {e}")
        if i % 10 == 0:
            print(f"  进度 {i}/{total}")

    print(f"[done] 上传 {uploaded}，跳过 {skipped}，失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
