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


async def hybrid_ipfs_upload(metadata):
    """
    Tries Local Node first, then falls back to Pinata API.
    Ensures sessions are closed to prevent 'Unclosed client session' errors.
    """
    client = aioipfs.AsyncIPFS(maddr='/ip4/127.0.0.1/tcp/5001', read_timeout=5)
    try:
        print("🔍 Checking local IPFS node...")
        # Check connection
        await client.core.id() 
        
        print("✅ Local node active. Uploading...")
        # Change this line in hybrid_ipfs_upload:
        added_res = await client.add_str(json.dumps(metadata, cls=DecimalEncoder))
        return added_res['Hash']
        
    except Exception as e:
        print(f"⚠️ Local node unavailable: {e}. Falling back to Pinata...")
        
        url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config("PINATA_JWT")}'
        }
        # 1. Convert your metadata to a JSON string manually using the Encoder
        # This handles all the Decimal(12.5) or Decimal(42000) objects
        json_payload = json.dumps(
            {"pinataContent": metadata}, 
            cls=DecimalEncoder
        )

        # 2. Use 'data' instead of 'json' in the requests call
        response = requests.post(
            url, 
            headers=headers, 
            data=json_payload  # Send the pre-serialized string
        )
        if response.status_code == 200:
            return response.json()['IpfsHash']
        else:
            raise Exception(f"❌ Both IPFS paths failed. Pinata status: {response.status_code}")
    
    finally:
        # CRITICAL: This closes the aiohttp session properly
        await client.close()

