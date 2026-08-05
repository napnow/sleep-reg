"""
Convert ChatGPT SSO/tokens to auth JSON format.
Similar to grokRegister-cpa sso_to_auth_json.py

This can be used to convert existing tokens or integrate
with other tools that expect specific auth formats.
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


def convert_to_auth_format(
    email: str,
    password: str,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    id_token: Optional[str] = None,
    additional_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Convert registration result to standard auth JSON format.

    This format can be used with various proxy/tools that
    expect OpenAI-compatible authentication.
    """
    auth_data = {
        "type": "openai",
        "email": email,
        "password": password,
        "created_at": datetime.now().isoformat(),
    }

    # Add tokens if available
    if access_token:
        auth_data["access_token"] = access_token
    if refresh_token:
        auth_data["refresh_token"] = refresh_token
    if id_token:
        auth_data["id_token"] = id_token

    # Add any additional data
    if additional_data:
        auth_data.update(additional_data)

    return auth_data


def convert_file(input_path: Path, output_dir: Path = None) -> Optional[Path]:
    """Convert a single registration result file."""
    try:
        with open(input_path) as f:
            data = json.load(f)

        email = data.get("email")
        if not email:
            print(f"Skipping {input_path}: no email found")
            return None

        # Convert to auth format
        auth_data = convert_to_auth_format(
            email=email,
            password=data.get("password", ""),
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            id_token=data.get("id_token"),
            additional_data={
                k: v for k, v in data.items()
                if k not in ["email", "password", "access_token", "refresh_token", "id_token", "type"]
            }
        )

        # Determine output path
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_email = email.replace("@", "_at_").replace(".", "_")
            output_path = output_dir / f"openai_{safe_email}.json"
        else:
            # Save alongside input with new name
            output_path = input_path.parent / f"auth_{input_path.name}"

        with open(output_path, "w") as f:
            json.dump(auth_data, f, indent=2)

        print(f"Converted: {input_path} -> {output_path}")
        return output_path

    except Exception as e:
        print(f"Error converting {input_path}: {e}")
        return None


def scan_and_convert(
    source: Path,
    output_dir: Path = None,
    pattern: str = "*.json"
) -> List[Path]:
    """Scan directory for registration results and convert them."""
    if source.is_file():
        result = convert_file(source, output_dir)
        return [result] if result else []

    converted = []
    for json_file in source.glob(pattern):
        # Skip already converted files
        if json_file.name.startswith("auth_"):
            continue

        # Check if it looks like a registration result
        try:
            with open(json_file) as f:
                data = json.load(f)
            if "email" in data and ("password" in data or "access_token" in data):
                result = convert_file(json_file, output_dir)
                if result:
                    converted.append(result)
        except:
            continue

    return converted


def main():
    parser = argparse.ArgumentParser(
        description="Convert ChatGPT registration results to auth format"
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=".",
        help="Source file or directory (default: current dir)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory (default: same as source)"
    )
    parser.add_argument(
        "--pattern",
        default="chatgpt_*.json",
        help="File pattern to match (default: chatgpt_*.json)"
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="Treat source as single file, not directory"
    )

    args = parser.parse_args()

    source = Path(args.source)
    output_dir = Path(args.output) if args.output else None

    if args.single or source.is_file():
        result = convert_file(source, output_dir)
        if result:
            print(f"\nConversion complete: 1 file converted")
    else:
        converted = scan_and_convert(source, output_dir, args.pattern)
        print(f"\nConversion complete: {len(converted)} files converted")

        if converted:
            print("\nConverted files:")
            for path in converted:
                print(f"  {path}")


if __name__ == "__main__":
    main()
