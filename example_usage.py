"""
Example: Direct usage of ChatGPT protocol signup.

This shows how to use the registration components programmatically
without the GUI or CLI.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from email_providers import DuckMailProvider
from protocol.gpt_register import GPTRegistrar


def example_simple_registration():
    """Example of simple single registration."""

    # 1. Create email provider
    email_provider = DuckMailProvider({})

    # 2. Create email
    print("Creating temporary email...")
    email = email_provider.create_email()
    print(f"Email: {email}")

    # 3. Generate password
    import random
    import string
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    print(f"Password: {password}")

    # 4. Create registrar
    registrar = GPTRegistrar(
        email_provider=email_provider,
        proxy="",  # Add proxy URL if needed, e.g., "http://127.0.0.1:7890"
        on_log=lambda msg: print(f"[LOG] {msg}"),
        on_progress=lambda msg: print(f"[PROGRESS] {msg}")
    )

    # 5. Perform registration
    print(f"\nStarting registration for {email}...")
    result = registrar.register(email=email, password=password)

    # 6. Handle result
    if result:
        print("\n✓ Registration successful!")
        print(f"Email: {result['email']}")
        print(f"Access token: {result.get('access_token', 'N/A')[:30]}...")

        # Save result
        import json
        output_file = f"account_{email.replace('@', '_at_').replace('.', '_')}.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResult saved to {output_file}")
    else:
        print("\n✗ Registration failed")

    return result


def example_with_proxy():
    """Example with proxy configuration."""
    email_provider = DuckMailProvider({})

    registrar = GPTRegistrar(
        email_provider=email_provider,
        proxy="http://127.0.0.1:7890",  # Your proxy
        on_log=lambda msg: print(f"[LOG] {msg}"),
        on_progress=lambda msg: print(f"[PROGRESS] {msg}"),
    )

    email = email_provider.create_email()
    password = "YourSecurePassword123!"

    result = registrar.register(email=email, password=password)

    return result


if __name__ == "__main__":
    print("ChatGPT GPTRegistrar Example")
    print("=" * 40)

    # Run simple example
    try:
        result = example_simple_registration()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
