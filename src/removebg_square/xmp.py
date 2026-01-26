from __future__ import annotations

import struct
import zlib
import xml.etree.ElementTree as ET
from datetime import date as _date
from pathlib import Path
from typing import Optional, Union

DEFAULT_PROCESS_TOOL = "removebg-square-cli"

_NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def _ensure_ns(prefix: str, uri: str):
    try:
        ET.register_namespace(prefix, uri)
    except Exception:
        pass


_ensure_ns("x", _NS["x"])
_ensure_ns("rdf", _NS["rdf"])
_ensure_ns("dc", _NS["dc"])


def _minimal_xmp_packet_root() -> ET.Element:
    xmpmeta = ET.Element(f"{{{_NS['x']}}}xmpmeta")
    rdf = ET.SubElement(xmpmeta, f"{{{_NS['rdf']}}}RDF")
    ET.SubElement(rdf, f"{{{_NS['rdf']}}}Description")
    return xmpmeta


def _get_or_create_rdf_description(xmpmeta_root: ET.Element) -> ET.Element:
    rdf = None
    for el in xmpmeta_root.iter():
        if el.tag == f"{{{_NS['rdf']}}}RDF":
            rdf = el
            break
    if rdf is None:
        rdf = ET.SubElement(xmpmeta_root, f"{{{_NS['rdf']}}}RDF")

    for el in list(rdf):
        if el.tag == f"{{{_NS['rdf']}}}Description":
            return el

    return ET.SubElement(rdf, f"{{{_NS['rdf']}}}Description")


def _find_child(parent: ET.Element, ns: str, name: str) -> Optional[ET.Element]:
    tag = f"{{{ns}}}{name}"
    for ch in list(parent):
        if ch.tag == tag:
            return ch
    return None


def _ensure_dc_subject_keyword(desc: ET.Element, keyword: str) -> bool:
    changed = False

    dc_subject = _find_child(desc, _NS["dc"], "subject")
    if dc_subject is None:
        dc_subject = ET.SubElement(desc, f"{{{_NS['dc']}}}subject")
        changed = True

    bag = None
    for ch in list(dc_subject):
        if ch.tag == f"{{{_NS['rdf']}}}Bag":
            bag = ch
            break
    if bag is None:
        bag = ET.SubElement(dc_subject, f"{{{_NS['rdf']}}}Bag")
        changed = True

    for li in list(bag):
        if li.tag == f"{{{_NS['rdf']}}}li" and (li.text or "").strip() == keyword:
            return changed

    li = ET.SubElement(bag, f"{{{_NS['rdf']}}}li")
    li.text = keyword
    return True


def _ensure_dc_description_xdefault(desc: ET.Element, text: str) -> bool:
    changed = False

    dc_desc = _find_child(desc, _NS["dc"], "description")
    if dc_desc is None:
        dc_desc = ET.SubElement(desc, f"{{{_NS['dc']}}}description")
        changed = True

    alt = None
    for ch in list(dc_desc):
        if ch.tag == f"{{{_NS['rdf']}}}Alt":
            alt = ch
            break
    if alt is None:
        alt = ET.SubElement(dc_desc, f"{{{_NS['rdf']}}}Alt")
        changed = True

    xml_lang_key = "{http://www.w3.org/XML/1998/namespace}lang"
    for li in list(alt):
        if li.tag != f"{{{_NS['rdf']}}}li":
            continue
        lang = (li.attrib.get(xml_lang_key, "") or "").strip().lower()
        if lang == "x-default":
            if (li.text or "") == text:
                return changed
            li.text = text
            return True

    li = ET.SubElement(alt, f"{{{_NS['rdf']}}}li")
    li.set(xml_lang_key, "x-default")
    li.text = text
    return True


def _decode_xml_bytes(xmp_xml_bytes: bytes) -> Optional[str]:
    if not xmp_xml_bytes:
        return None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return xmp_xml_bytes.decode(enc, errors="replace")
        except Exception:
            continue
    return None


def _parse_or_create_xmpmeta_root(xmp_xml_bytes: Optional[bytes]) -> ET.Element:
    if xmp_xml_bytes:
        txt = _decode_xml_bytes(xmp_xml_bytes)
        if txt:
            try:
                root = ET.fromstring(txt)
                if root.tag.endswith("xmpmeta"):
                    return root
                for el in root.iter():
                    if el.tag.endswith("xmpmeta"):
                        return el
            except Exception:
                pass
    return _minimal_xmp_packet_root()


def _serialize_xmpmeta(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _make_updated_xmp_packet(
    existing_xmp: Optional[bytes], *, tool: str, processed_date: str
) -> bytes:
    keyword = f"ProcessedWith:{tool}"
    desc_text = f"Processed by {tool} on {processed_date}"

    root = _parse_or_create_xmpmeta_root(existing_xmp)
    rdf_desc = _get_or_create_rdf_description(root)

    _ensure_dc_subject_keyword(rdf_desc, keyword)
    _ensure_dc_description_xdefault(rdf_desc, desc_text)

    return _serialize_xmpmeta(root)


_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_XMP_ITXT_KEYWORD = b"XML:com.adobe.xmp"


def _iter_png_chunks(data: bytes):
    if not data.startswith(_PNG_SIG):
        return
    i = len(_PNG_SIG)
    n = len(data)
    while i + 8 <= n:
        if i + 8 > n:
            return
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        data_start = i + 8
        data_end = data_start + length
        crc_end = data_end + 4
        chunk_start = i
        chunk_end = crc_end
        if crc_end > n:
            return
        yield (ctype, data_start, data_end, chunk_start, chunk_end)
        i = chunk_end
        if ctype == b"IEND":
            return


def _build_png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    length = struct.pack(">I", len(payload))
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
    crc_bytes = struct.pack(">I", crc)
    return length + chunk_type + payload + crc_bytes


def _build_png_itxt_xmp_chunk(xmp_packet: bytes) -> bytes:
    keyword = _XMP_ITXT_KEYWORD
    if len(keyword) < 1 or len(keyword) > 79:
        raise ValueError("Invalid iTXt keyword length")

    compression_flag = b"\x00"
    compression_method = b"\x00"
    language_tag = b"" + b"\x00"
    translated_keyword = b"" + b"\x00"

    payload = (
        keyword
        + b"\x00"
        + compression_flag
        + compression_method
        + language_tag
        + translated_keyword
        + xmp_packet
    )
    return _build_png_chunk(b"iTXt", payload)


def _extract_png_itxt_xmp_packet(data: bytes) -> Optional[bytes]:
    for ctype, ds, de, _, _ in _iter_png_chunks(data):
        if ctype != b"iTXt":
            continue
        payload = data[ds:de]
        nul = payload.find(b"\x00")
        if nul <= 0:
            continue
        keyword = payload[:nul]
        if keyword != _XMP_ITXT_KEYWORD:
            continue

        j = nul + 1
        if j + 2 > len(payload):
            continue
        j += 2

        nul2 = payload.find(b"\x00", j)
        if nul2 == -1:
            continue
        j = nul2 + 1

        nul3 = payload.find(b"\x00", j)
        if nul3 == -1:
            continue
        j = nul3 + 1

        return payload[j:] if j <= len(payload) else b""

    return None


def write_processed_xmp_embed_png(
    png_path: Union[str, Path],
    *,
    tool: str = DEFAULT_PROCESS_TOOL,
    processed_date: Optional[str] = None,
) -> bool:
    p = Path(png_path)
    if p.suffix.lower() != ".png":
        return False

    processed_date = processed_date or _date.today().isoformat()

    try:
        data = p.read_bytes()
    except Exception:
        return False

    if not data.startswith(_PNG_SIG):
        return False

    existing_xmp = _extract_png_itxt_xmp_packet(data)
    new_xmp_packet = _make_updated_xmp_packet(
        existing_xmp, tool=tool, processed_date=processed_date
    )
    new_itxt = _build_png_itxt_xmp_chunk(new_xmp_packet)

    replace_start = None
    replace_end = None
    insert_at = None

    for ctype, _, _, chunk_start, chunk_end in _iter_png_chunks(data):
        if ctype == b"iTXt":
            payload = data[chunk_start + 8 : chunk_end - 4]
            nul = payload.find(b"\x00")
            if nul > 0 and payload[:nul] == _XMP_ITXT_KEYWORD:
                replace_start = chunk_start
                replace_end = chunk_end
                break

        if ctype == b"IEND":
            insert_at = chunk_start
            break

    if replace_start is not None and replace_end is not None:
        new_data = data[:replace_start] + new_itxt + data[replace_end:]
    else:
        if insert_at is None:
            return False
        new_data = data[:insert_at] + new_itxt + data[insert_at:]

    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        tmp.write_bytes(new_data)
        tmp.replace(p)
        return True
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def _sidecar_path_for_image(image_path: Path) -> Path:
    return image_path.with_name(image_path.name + ".xmp")


def write_processed_xmp_sidecar(
    image_path: Union[str, Path],
    *,
    tool: str = DEFAULT_PROCESS_TOOL,
    processed_date: Optional[str] = None,
) -> bool:
    p = Path(image_path)
    processed_date = processed_date or _date.today().isoformat()

    sidecar = _sidecar_path_for_image(p)

    existing = None
    if sidecar.exists():
        try:
            existing = sidecar.read_bytes()
        except Exception:
            existing = None

    root = _parse_or_create_xmpmeta_root(existing)
    rdf_desc = _get_or_create_rdf_description(root)

    changed = False
    changed = _ensure_dc_subject_keyword(rdf_desc, f"ProcessedWith:{tool}") or changed
    changed = (
        _ensure_dc_description_xdefault(
            rdf_desc, f"Processed by {tool} on {processed_date}"
        )
        or changed
    )

    if not changed and sidecar.exists():
        return True

    try:
        sidecar.write_bytes(_serialize_xmpmeta(root))
        return True
    except Exception:
        return False


def write_processed_tags(
    image_path: Union[str, Path],
    *,
    tool: str = DEFAULT_PROCESS_TOOL,
    processed_date: Optional[str] = None,
    embed_png: bool = True,
    also_write_sidecar: bool = False,
) -> bool:
    p = Path(image_path)
    processed_date = processed_date or _date.today().isoformat()

    ok_any = False

    if p.suffix.lower() == ".png" and embed_png:
        ok_any = (
            write_processed_xmp_embed_png(p, tool=tool, processed_date=processed_date)
            or ok_any
        )

    if also_write_sidecar or p.suffix.lower() != ".png":
        ok_any = (
            write_processed_xmp_sidecar(p, tool=tool, processed_date=processed_date)
            or ok_any
        )

    return ok_any
