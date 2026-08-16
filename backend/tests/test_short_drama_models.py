"""V2.1 短剧领域模型与关键数据库约束。"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Episode,
    ProjectBrief,
    Resource,
    Scene,
    ShortDramaProject,
    Shot,
    StoryVersion,
    Take,
    User,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_short_drama_metadata_contains_domain_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    expected = {
        "short_drama_projects",
        "project_briefs",
        "drama_episodes",
        "drama_scenes",
        "story_versions",
        "drama_shots",
        "drama_takes",
        "drama_characters",
        "character_variants",
        "drama_locations",
        "drama_props",
        "creative_jobs",
        "project_resource_links",
        "shot_task_links",
    }

    assert expected <= set(inspector.get_table_names())
    for table in expected:
        assert "owner_id" in {column["name"] for column in inspector.get_columns(table)}


def test_project_storyboard_hierarchy_persists(db: Session) -> None:
    user = User(username="drama-owner", password_hash="hash", role="user", status="active")
    db.add(user)
    db.flush()
    project = ShortDramaProject(owner_id=user.id, name="第一部短剧")
    project.brief = ProjectBrief(owner_id=user.id, genre="悬疑", aspect_ratio="9:16")
    episode = Episode(owner_id=user.id, number=1, title="第一集", sort_order=0)
    scene = Scene(owner_id=user.id, scene_no="1", heading="旧仓库·夜", sort_order=0)
    version = StoryVersion(owner_id=user.id, version=1, name="初稿", is_current=True)
    shot = Shot(owner_id=user.id, shot_no=1, visual_description="角色推开仓库门", sort_order=0)
    project.episodes.append(episode)
    project.story_versions.append(version)
    episode.scenes.append(scene)
    scene.shots.append(shot)
    db.add(project)
    db.commit()

    persisted = db.get(ShortDramaProject, project.id)
    assert persisted is not None
    assert persisted.brief is not None
    assert persisted.brief.genre == "悬疑"
    assert persisted.episodes[0].scenes[0].shots[0].visual_description == "角色推开仓库门"
    assert persisted.story_versions[0].is_current is True


def test_only_one_take_can_be_selected_per_shot(db: Session) -> None:
    user = User(username="take-owner", password_hash="hash", role="user", status="active")
    resource_one = Resource(
        owner_id=None,
        filename="take-1.png",
        storage_key="tests/take-1.png",
        media_type="image",
        direction="output",
    )
    resource_two = Resource(
        owner_id=None,
        filename="take-2.png",
        storage_key="tests/take-2.png",
        media_type="image",
        direction="output",
    )
    db.add_all([user, resource_one, resource_two])
    db.flush()
    resource_one.owner_id = user.id
    resource_two.owner_id = user.id
    project = ShortDramaProject(owner_id=user.id, name="Take 约束")
    episode = Episode(owner_id=user.id, number=1)
    scene = Scene(owner_id=user.id, scene_no="1")
    shot = Shot(owner_id=user.id, shot_no=1)
    project.episodes.append(episode)
    episode.scenes.append(scene)
    scene.shots.append(shot)
    db.add(project)
    db.flush()
    db.add(Take(owner_id=user.id, shot_id=shot.id, resource_id=resource_one.id, take_no=1, is_selected=True))
    db.commit()

    db.add(Take(owner_id=user.id, shot_id=shot.id, resource_id=resource_two.id, take_no=2, is_selected=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
