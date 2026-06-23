from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.panel.auth import verify_panel_token
from src import stats

router = APIRouter(prefix="/stats")


@router.get("")
async def get_model_stats(token: str = Depends(verify_panel_token)):
    return JSONResponse(content=await stats.get_stats())
