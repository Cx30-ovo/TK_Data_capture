from fastapi import APIRouter,HTTPException,Query
from config.db_config import sqlite_db_config
from database.topic_monitor_repository import TopicError
from ..services import topic_monitor_service as service

router=APIRouter(prefix='/topic-monitors',tags=['topic-monitors'])


async def action(fn):
    try:return await fn()
    except TopicError as exc:raise HTTPException(exc.status,str(exc)) from exc


@router.get('')
async def list_topics():
    return await action(lambda:service.listing(sqlite_db_config['db_path']))


@router.post('')
async def create_topic(request:service.TopicCreate):
    return await action(lambda:service.create(sqlite_db_config['db_path'],request))


@router.put('/{topic_id}')
async def update_topic(topic_id:str,request:service.TopicUpdate):
    return await action(lambda:service.update(sqlite_db_config['db_path'],topic_id,request))


@router.get('/{topic_id}')
async def topic_detail(topic_id:str,page:int=Query(1,ge=1,le=100000),sort:str=Query('heat')):
    return await action(lambda:service.detail(sqlite_db_config['db_path'],topic_id,page,sort))


@router.delete('/{topic_id}')
async def delete_topic(topic_id:str,expected_version:int=Query(...,ge=1)):
    return await action(lambda:service.delete(sqlite_db_config['db_path'],topic_id,expected_version))
