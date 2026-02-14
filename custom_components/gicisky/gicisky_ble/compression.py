"""
Compression utilities for BLE image transfer.

표준 QuickLZ Level 1 (1.5.x) 호환 구현.
- 64바이트 청크 단위 독립 압축
- 0x75: 압축 청크 (QuickLZ L1), 0x74: 비압축 청크 (raw)
- 12비트 해시 기반 매치 (직접 오프셋 아님)
- Short match (2B): bits 0-3 = matchlen-2, bits 4-15 = hash
- Long match (3B): bits 0-3 = 0, bits 4-15 = hash, byte2 = matchlen
"""
from __future__ import annotations

import struct

_CWORD_LEN = 4
_HASH_VALUES = 4096
_MINOFFSET = 2
_UNCONDITIONAL_MATCHLEN_COMPRESSOR = 12
_UNCOMPRESSED_END = 4
_CHUNK_SIZE = 64


# ---------------------------------------------------------------------------
# 해시 함수 (QuickLZ L1 표준)
# ---------------------------------------------------------------------------
def _hash_func(fetch: int) -> int:
    return ((fetch >> 12) ^ fetch) & (_HASH_VALUES - 1)


def _fast_read_3(data, pos: int) -> int:
    """3바이트를 LE uint24로 읽기."""
    if pos + 3 > len(data):
        return 0
    return data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16)


def _same(data, pos: int, n: int) -> bool:
    """pos에서 n+1 바이트가 모두 동일한지 확인."""
    if pos < 0 or pos + n >= len(data):
        return False
    v = data[pos]
    for i in range(1, n + 1):
        if data[pos + i] != v:
            return False
    return True


# ---------------------------------------------------------------------------
# QuickLZ L1 단일 청크 압축
# ---------------------------------------------------------------------------
def _qlz_compress_core(source) -> bytes | None:
    """
    QuickLZ Level 1 core 압축.
    압축이 이득이 없으면 None 반환.
    """
    size = len(source)
    last_byte_idx = size - 1
    last_matchstart = last_byte_idx - _UNCONDITIONAL_MATCHLEN_COMPRESSOR - _UNCOMPRESSED_END

    if last_matchstart < 0:
        return None  # 너무 작아서 압축 불가

    out = bytearray(size * 2 + 400)
    cword_ptr = 0
    dst = _CWORD_LEN
    cword_val = 1 << 31
    src = 0
    lits = 0

    # 해시 테이블: offset, cache
    h_offset = [0] * _HASH_VALUES
    h_cache = [0] * _HASH_VALUES

    while src <= last_matchstart:
        # cword 플러시 검사
        if (cword_val & 1) == 1:
            # 압축률 검사
            if src > (size >> 1) and (dst > src - (src >> 5)):
                return None
            struct.pack_into("<I", out, cword_ptr, (cword_val >> 1) | (1 << 31))
            cword_ptr = dst
            dst += _CWORD_LEN
            cword_val = 1 << 31

        fetch = _fast_read_3(source, src)
        h = _hash_func(fetch)
        cached = fetch ^ h_cache[h]
        h_cache[h] = fetch
        o = h_offset[h]
        h_offset[h] = src

        dist = src - o
        if (cached & 0xFFFFFF) == 0 and o != 0 and (
            dist > _MINOFFSET
            or (
                src == o + 1
                and lits >= 3
                and src > 3
                and _same(source, src - 3, 6)
            )
        ):
            # 매치 발견
            matchlen = 3
            remaining = min(255, last_byte_idx - _UNCOMPRESSED_END - src + 1)
            while matchlen < remaining and source[src + matchlen] == source[o + matchlen]:
                matchlen += 1

            h_shifted = h << 4
            cword_val = (cword_val >> 1) | (1 << 31)

            if matchlen < 18:
                # Short match: 2바이트
                val = (matchlen - 2) | h_shifted
                out[dst] = val & 0xFF
                out[dst + 1] = (val >> 8) & 0xFF
                dst += 2
            else:
                # Long match: 3바이트
                out[dst] = h_shifted & 0xFF
                out[dst + 1] = (h_shifted >> 8) & 0xFF
                out[dst + 2] = matchlen & 0xFF
                dst += 3

            src += matchlen
            lits = 0
        else:
            # 리터럴
            lits += 1
            out[dst] = source[src]
            src += 1
            dst += 1
            cword_val = cword_val >> 1

    # 나머지 바이트들 (리터럴)
    while src <= last_byte_idx:
        if (cword_val & 1) == 1:
            struct.pack_into("<I", out, cword_ptr, (cword_val >> 1) | (1 << 31))
            cword_ptr = dst
            dst += _CWORD_LEN
            cword_val = 1 << 31

        # 해시 업데이트 (마지막 3바이트 이전까지)
        if src <= last_byte_idx - 2:
            f = _fast_read_3(source, src)
            hh = _hash_func(f)
            h_cache[hh] = f
            h_offset[hh] = src

        out[dst] = source[src]
        src += 1
        dst += 1
        cword_val = cword_val >> 1

    # 최종 cword 플러시
    while (cword_val & 1) != 1:
        cword_val = cword_val >> 1
    struct.pack_into("<I", out, cword_ptr, (cword_val >> 1) | (1 << 31))

    compressed_size = dst
    if compressed_size >= size:
        return None  # 압축 이득 없음

    return bytes(out[:compressed_size])


# ---------------------------------------------------------------------------
# QuickLZ L1 단일 청크 해제
# ---------------------------------------------------------------------------
def _update_hash(out, hash_offset, last_hashed: int, limit: int, dest_size: int) -> int:
    """해시 테이블 업데이트: last_hashed+1 부터 limit 까지. 갱신된 last_hashed 반환."""
    while last_hashed < limit:
        pos = last_hashed + 1
        if pos + 3 > dest_size:
            break
        fh = out[pos] | (out[pos + 1] << 8) | (out[pos + 2] << 16)
        hh = _hash_func(fh)
        hash_offset[hh] = pos
        last_hashed = pos
    return last_hashed


def _qlz_decompress_core(stream, dest_size: int) -> bytes:
    """
    QuickLZ Level 1 core 해제.
    표준 QuickLZ 해시 기반 매치 복원.
    stream: compressed core data (헤더 제외).
    dest_size: 복원 크기 (보통 64).
    """
    out = bytearray(dest_size)
    dst = 0
    src = 0
    n = len(stream)
    last_dst = dest_size - 1
    cword_val = 1

    # 해시 테이블 (디코더): hash → 출력 위치
    hash_offset: list[int] = [0] * _HASH_VALUES
    last_hashed = -1

    while dst <= last_dst:
        # cword 재로드
        if cword_val == 1:
            if src + _CWORD_LEN > n:
                break
            cword_val = struct.unpack("<I", stream[src : src + _CWORD_LEN])[0]
            src += _CWORD_LEN

        if (cword_val & 1) == 1:
            # 매치
            cword_val >>= 1
            if src + 2 > n:
                break
            fetch_lo = stream[src] | (stream[src + 1] << 8)
            h = (fetch_lo >> 4) & 0xFFF
            matchlen_indicator = fetch_lo & 0xF

            if matchlen_indicator != 0:
                matchlen = matchlen_indicator + 2
                src += 2
            else:
                if src + 3 > n:
                    break
                matchlen = stream[src + 2]
                src += 3

            # 매치 전 해시 업데이트: dst - 3 까지 (안전한 범위)
            safe_limit = dst - 3
            if safe_limit > last_hashed:
                last_hashed = _update_hash(out, hash_offset, last_hashed, safe_limit, dest_size)

            # 해시 테이블에서 소스 위치 조회
            offset2 = hash_offset[h]

            # 매치 복사
            match_start = dst
            for _ in range(matchlen):
                if dst > last_dst:
                    break
                if 0 <= offset2 < dest_size:
                    out[dst] = out[offset2]
                offset2 += 1
                dst += 1

            # 매치 후 해시 업데이트: match_start 까지 (복사된 데이터 포함)
            last_hashed = _update_hash(out, hash_offset, last_hashed, match_start, dest_size)
            last_hashed = dst - 1
        else:
            # 리터럴
            cword_val >>= 1
            if src >= n:
                break
            out[dst] = stream[src]
            dst += 1
            src += 1

    return bytes(out[:dest_size])


# ---------------------------------------------------------------------------
# 청크 단위 압축/해제 래퍼
# ---------------------------------------------------------------------------
def _compress_chunked(data: bytes, force_raw: bool = False) -> bytes:
    """
    64바이트 청크마다 QuickLZ L1 압축.
    0x75: 압축 청크, 0x74: 비압축 청크 (raw).
    force_raw=True이면 모든 청크를 0x74 (raw)로 전송.
    """
    output = bytearray()
    for i in range(0, len(data), _CHUNK_SIZE):
        chunk = data[i : i + _CHUNK_SIZE]
        n = len(chunk)
        compressed = None if force_raw else _qlz_compress_core(chunk)
        if compressed is not None:
            # 압축 청크
            total_len = 3 + len(compressed)
            output.append(0x75)
            output.append(total_len & 0xFF)
            output.append(n & 0xFF)
            output.extend(compressed)
        else:
            # 비압축 청크 (raw)
            total_len = 3 + n
            output.append(0x74)
            output.append(total_len & 0xFF)
            output.append(n & 0xFF)
            output.extend(chunk)
    return bytes(output)


def compress(data: bytes, force_raw: bool = False) -> bytes:
    """
    compress2 형식: 반으로 나눈 뒤 각 part를 64바이트 청크 QuickLZ L1으로 인코딩.
    출력: [4B LE part2 원본 길이] + part1 청크들 + part2 청크들.
    force_raw=True이면 모든 청크를 0x74 (raw)로 전송 (QuickLZ 비사용).
    """
    total_len = len(data)
    split = total_len // 2
    part1 = data[:split]
    part2 = data[split:]
    compressed_part1 = _compress_chunked(part1, force_raw=force_raw)
    compressed_part2 = _compress_chunked(part2, force_raw=force_raw)
    header = struct.pack("<I", len(part2))
    return header + compressed_part1 + compressed_part2


def _decompress_chunks(payload: bytes, start: int, max_bytes: int) -> tuple[bytes, int]:
    """
    청크 스트림 해제. start 위치부터 max_bytes 만큼 해제 후 (결과, 소비 위치) 반환.
    """
    out = bytearray()
    pos = start
    while pos + 3 <= len(payload) and len(out) < max_bytes:
        magic = payload[pos]
        if magic not in (0x74, 0x75):
            pos += 1
            continue
        total_len = payload[pos + 1]
        if total_len < 6 or total_len > 80:
            # 최소 6 (3헤더+최소 데이터), 최대 ~80 (압축 오버헤드 포함).
            pos += 1
            continue
        if pos + total_len > len(payload):
            break
        uncompressed_size = payload[pos + 2]
        if uncompressed_size != _CHUNK_SIZE:
            # 모든 유효 청크는 64바이트 해제
            pos += 1
            continue
        stream = payload[pos + 3 : pos + total_len]
        if magic == 0x74:
            out.extend(stream[:uncompressed_size])
        else:
            chunk = _qlz_decompress_core(stream, uncompressed_size)
            out.extend(chunk)
        pos += total_len
    return bytes(out[:max_bytes]), pos


def decompress(payload: bytes) -> bytes:
    """
    compress2 형식 역연산: [4B part2 길이] + 0x74/0x75 청크들 → 원본 바이트.
    0x74: 비압축 (raw 복사), 0x75: QuickLZ L1 해제.
    part2_len으로 part 경계를 올바르게 분리.
    """
    if len(payload) < 4:
        return b""
    part2_len = struct.unpack("<I", payload[:4])[0]
    if part2_len == 0:
        part2_len = len(payload)  # fallback
    part1_len = part2_len  # 대칭 분할
    part1, next_pos = _decompress_chunks(payload, 4, part1_len)
    part2, _ = _decompress_chunks(payload, next_pos, part2_len)
    return part1 + part2
