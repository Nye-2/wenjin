"""ViewImageMiddleware - injects viewed images into conversation for vision models.

When the model supports vision (supports_vision=True) and there are viewed_images
in state, this middleware injects them as HumanMessage with image content before
the model processes messages.

After model processing, the viewed_images are cleared to prevent re-injection.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


class ViewImageMiddleware(Middleware):
    """Middleware that injects viewed images for vision-enabled models.

    Behavior:
    - before_model: If supports_vision and viewed_images exist, creates a
      HumanMessage with image content for each viewed image
    - after_model: Clears viewed_images to prevent re-injection in future turns

    Condition:
    - Only processes when config.configurable.supports_vision == True
    - Only processes when state.viewed_images is non-empty
    """

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Inject viewed images as HumanMessage content.

        Args:
            state: Current thread state containing viewed_images
            config: Runtime configuration with supports_vision flag

        Returns:
            Dict with messages containing image content, or empty dict if
            conditions are not met
        """
        # Check if vision is supported
        configurable = config.get("configurable", {})
        supports_vision = configurable.get("supports_vision", False)

        if not supports_vision:
            return {}

        # Check if there are viewed images
        viewed_images = state.get("viewed_images")
        if not viewed_images:
            return {}

        # Build image content list
        image_content: list[dict[str, Any]] = []
        for image_name, image_data in viewed_images.items():
            # Validate image data structure
            if not isinstance(image_data, dict):
                logger.warning(f"Invalid image data for '{image_name}': expected dict, got {type(image_data).__name__}")
                continue

            mime_type = image_data.get("mime_type")
            base64_data = image_data.get("base64")

            if not mime_type or not base64_data:
                logger.warning(f"Missing required keys in image data for '{image_name}': mime_type={bool(mime_type)}, base64={bool(base64_data)}")
                continue

            try:
                image_url = {
                    "url": f"data:{mime_type};base64,{base64_data}",
                }
                image_content.append({
                    "type": "image_url",
                    "image_url": image_url,
                })
            except Exception as e:
                logger.error(f"Failed to process image '{image_name}': {e}")
                continue

        if not image_content:
            return {}

        # Append a HumanMessage with image content instead of replacing the
        # existing conversation history.
        message = HumanMessage(content=image_content)
        existing_messages = list(state.get("messages", []))

        return {"messages": existing_messages + [message]}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Clear viewed_images after model processing.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Dict with empty viewed_images to clear the state
        """
        # Always clear viewed_images after model processes them
        return {"viewed_images": {}}
