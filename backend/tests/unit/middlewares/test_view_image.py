"""Tests for ViewImageMiddleware."""

import pytest

from src.agents.middlewares.view_image import ViewImageMiddleware
from src.agents.thread_state import ThreadState


@pytest.fixture
def middleware() -> ViewImageMiddleware:
    """Create ViewImageMiddleware instance."""
    return ViewImageMiddleware()


@pytest.fixture
def initial_state() -> ThreadState:
    """Create initial state without images."""
    return {
        "messages": [],
    }


@pytest.fixture
def state_with_image() -> ThreadState:
    """Create state with viewed images."""
    return {
        "messages": [],
        "viewed_images": {
            "image1.png": {
                "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "mime_type": "image/png",
            },
            "image2.jpg": {
                "base64": "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBEQACEQA/ALUABo//2Q==",
                "mime_type": "image/jpeg",
            },
        },
    }


@pytest.fixture
def vision_config() -> dict:
    """Create config with vision support enabled."""
    return {
        "configurable": {
            "supports_vision": True,
        },
    }


@pytest.fixture
def no_vision_config() -> dict:
    """Create config with vision support disabled."""
    return {
        "configurable": {
            "supports_vision": False,
        },
    }


class TestViewImageMiddleware:
    """Test cases for ViewImageMiddleware."""

    @pytest.mark.asyncio
    async def test_before_model_processes_images_with_vision(
        self,
        middleware: ViewImageMiddleware,
        state_with_image: ThreadState,
        vision_config: dict,
    ):
        """Verify that before_model processes images when vision is enabled."""
        # Act
        result = await middleware.before_model(state_with_image, vision_config)

        # Assert - should return HumanMessage with image content
        assert result is not None
        assert "messages" in result
        assert len(result["messages"]) == 1

        # Check the message contains image content
        message = result["messages"][0]
        assert hasattr(message, "content")

        # Content should be a list with image_url entries
        content = message.content
        assert isinstance(content, list)
        assert len(content) == 2  # Two images

        for item in content:
            assert "type" in item
            assert item["type"] == "image_url"
            assert "image_url" in item

    @pytest.mark.asyncio
    async def test_before_model_skips_without_vision(
        self,
        middleware: ViewImageMiddleware,
        state_with_image: ThreadState,
        no_vision_config: dict,
    ):
        """Verify that before_model skips processing when vision is disabled."""
        # Act
        result = await middleware.before_model(state_with_image, no_vision_config)

        # Assert - should return empty dict
        assert result == {}

    @pytest.mark.asyncio
    async def test_before_model_skips_without_images(
        self,
        middleware: ViewImageMiddleware,
        initial_state: ThreadState,
        vision_config: dict,
    ):
        """Verify that before_model skips processing when no images exist."""
        # Act
        result = await middleware.before_model(initial_state, vision_config)

        # Assert - should return empty dict
        assert result == {}

    @pytest.mark.asyncio
    async def test_after_model_returns_empty(
        self,
        middleware: ViewImageMiddleware,
        initial_state: ThreadState,
        vision_config: dict,
    ):
        """Verify that after_model returns dict to clear viewed_images."""
        # Act
        result = await middleware.after_model(initial_state, vision_config)

        # Assert - always clears viewed_images, even if empty
        assert result == {"viewed_images": {}}

    @pytest.mark.asyncio
    async def test_after_model_clears_viewed_images(
        self,
        middleware: ViewImageMiddleware,
        state_with_image: ThreadState,
        vision_config: dict,
    ):
        """Verify that after_model clears viewed_images from state."""
        # Act
        result = await middleware.after_model(state_with_image, vision_config)

        # Assert - should return empty viewed_images dict to clear them
        assert "viewed_images" in result
        assert result["viewed_images"] == {}
