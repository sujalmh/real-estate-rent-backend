from fastapi import APIRouter, Depends, Query, HTTPException
import httpx
from redis.asyncio import Redis
from app.core.redis import get_redis_client
from app.config import get_settings
import json

router = APIRouter()
settings = get_settings()

@router.get("/places/autocomplete")
async def places_autocomplete(
    input: str = Query(..., min_length=2),
    redis_client: Redis = Depends(get_redis_client)
):
    """
    Proxy for Google Places Autocomplete API.
    """
    if not settings.google_maps_api_key:
        raise HTTPException(status_code=500, detail="Google Maps API key not configured")

    # Update cache key to reflect granular query type if necessary
    cache_key = f"maps:places:granular:{input.lower()}"
    
    cached_response = await redis_client.get(cache_key)
    if cached_response:
        return json.loads(cached_response)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/autocomplete/json",
                params={
                    "input": input,
                    "key": settings.google_maps_api_key,
                    "components": "country:in",
                    # "types": "(regions)",  <-- REMOVED to allow granular results
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") in ["OK", "ZERO_RESULTS"]:
                await redis_client.setex(cache_key, 86400, json.dumps(data))
            
            return data
            
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Error contacting Google Maps API: {str(e)}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Google Maps API error: {e.response.text}")

@router.get("/geocode/reverse")
async def reverse_geocode(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    redis_client: Redis = Depends(get_redis_client)
):
    """
    Reverse geocode coordinates to address components.
    Returns city, state, postal_code, and formatted_address.
    """
    if not settings.google_maps_api_key:
        raise HTTPException(status_code=500, detail="Google Maps API key not configured")

    # Cache key with rounded coordinates for better cache hits
    cache_key = f"maps:geocode:{lat:.6f}:{lng:.6f}"
    
    cached_response = await redis_client.get(cache_key)
    if cached_response:
        return json.loads(cached_response)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "latlng": f"{lat},{lng}",
                    "key": settings.google_maps_api_key,
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                # Parse the first result for address components
                result = data["results"][0]
                address_components = result.get("address_components", [])
                
                # Extract relevant components
                city = None
                state = None
                postal_code = None
                district = None
                street = None
                
                for component in address_components:
                    types = component.get("types", [])
                    if "locality" in types:
                        city = component.get("long_name")
                    elif "administrative_area_level_1" in types:
                        state = component.get("long_name")
                    elif "administrative_area_level_2" in types:
                        district = component.get("long_name")
                    elif "postal_code" in types:
                        postal_code = component.get("long_name")
                    elif "route" in types or "street_number" in types:
                        if street:
                            street = f"{component.get('long_name')} {street}"
                        else:
                            street = component.get("long_name")
                
                response_data = {
                    "status": "OK",
                    "city": city,
                    "state": state,
                    "district": district,
                    "postal_code": postal_code,
                    "street": street,
                    "formatted_address": result.get("formatted_address"),
                    "raw": data  # Include raw response for debugging
                }
                
                # Cache for 30 days
                await redis_client.setex(cache_key, 2592000, json.dumps(response_data))
                
                return response_data
            else:
                return {
                    "status": data.get("status", "ERROR"),
                    "city": None,
                    "state": None,
                    "postal_code": None,
                    "formatted_address": None,
                }
            
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Error contacting Google Maps API: {str(e)}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Google Maps API error: {e.response.text}")

@router.get("/places/details/{place_id}")
async def place_details(
    place_id: str,
    redis_client: Redis = Depends(get_redis_client)
):
    """
    Get place details (geometry) from Google Places API.
    """
    if not settings.google_maps_api_key:
        raise HTTPException(status_code=500, detail="Google Maps API key not configured")

    cache_key = f"maps:place_details:{place_id}"
    
    cached_response = await redis_client.get(cache_key)
    if cached_response:
        return json.loads(cached_response)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params={
                    "place_id": place_id,
                    "fields": "geometry",
                    "key": settings.google_maps_api_key,
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "OK":
                # Cache for 30 days (place geometry rarely changes)
                await redis_client.setex(cache_key, 2592000, json.dumps(data))
                return data
            else:
                return {
                    "status": data.get("status", "ERROR"),
                    "result": None
                }
            
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Error contacting Google Maps API: {str(e)}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Google Maps API error: {e.response.text}")