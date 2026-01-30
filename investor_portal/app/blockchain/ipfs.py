import aioipfs
import requests
import json
from decouple import config
from app.services.helpers import DecimalEncoder
from tenacity import retry, stop_after_attempt, wait_fixed

# ------------------------------------------------------------------
# 1.  Plain-gateway fetch (any public or local node)
# ------------------------------------------------------------------
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def _fetch_from_gateway(cid, gateway="https://ipfs.io/ipfs"):
    """Raw GET -> decoded JSON dict"""
    url = f"{gateway}/{cid}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------
# 2. Corrected Pinata Dedicated Gateway Fetch
# ------------------------------------------------------------------
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def _fetch_from_pinata_gateway(cid):
    # REPLACE with your actual dedicated gateway domain from Pinata Dashboard
    # Example: "aquamarine-casual-tarantula-177.mypinata.cloud"
    dedicated_domain = config('PINATA_GATEWAY_DOMAIN')
    
    url = f"https://{dedicated_domain}/ipfs/{cid}"
    params = {
        "pinataGatewayToken": config('PINATA_GATEWAY_KEY')
    }
    resp = requests.get(url, params=params, timeout=10)
    
    # If it fails here, it might be because the CID is not pinned to your account
    # and your gateway is in 'Restricted' mode.
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------
# 3.  Public helper – “download metadata for this loan”
# ------------------------------------------------------------------
def fetch_loan_metadata(cid: str) -> dict:
    # 1. Try Authenticated Dedicated Gateway (Fastest)
    try:
        return _fetch_from_pinata_gateway(cid)
    except Exception as e:
        print(f"DEBUG: Dedicated Gateway check failed for {cid}: {e}")

    # 2. Try Public Pinata Gateway (No JWT, slower)
    try:
        public_pinata = f"https://gateway.pinata.cloud/ipfs/{cid}"
        return requests.get(public_pinata, timeout=10).json()
    except Exception:
        pass

    # 3. Final Fallback: IPFS.io
    try:
        return _fetch_from_gateway(cid, "https://ipfs.io/ipfs")
    except Exception as e:
        raise RuntimeError(f"❌ Failed all gateways for CID {cid}") from e

