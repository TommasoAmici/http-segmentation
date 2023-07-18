import enum
import os
import uuid
from datetime import datetime
from http import HTTPStatus
from io import BytesIO
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

if TYPE_CHECKING:
    import numpy as np

KILL_AFTER_SECONDS = 120

s3_config = {
    "endpoint": os.environ["S3_ENDPOINT_URL"],
    "bucket": os.environ["S3_BUCKET"],
    "aws_access_key_id": os.environ["S3_ACCESS_KEY"],
    "aws_secret_access_key": os.environ["S3_SECRET_KEY"],
}

# global variable used to kill the container if no requests have been received
# in the last KILL_AFTER_SECONDS seconds
time_of_last_request = None


class ReturnType(enum.Enum):
    NO_MASK = 1
    SEGMENTED_IMAGE = 2
    ERROR = 3


class Segmentator:
    def __init__(self, image, resize: int | None = None) -> None:
        self.image = image
        self.resize = resize

    def find_masks(self):
        from ultralytics import YOLO

        model = YOLO(os.getenv("MODEL") or "yolov8x-seg.pt")
        [result] = model(self.image)
        return result

    def draw_mask(self, mask_array: "np.ndarray"):
        """
        Draws an image mask on a blank image and returns it.
        It converts the mask coordinates to an alpha mask.
        """
        from PIL import Image, ImageDraw

        # Create a blank mask image
        mask_image = Image.new("L", self.image.size, 0)
        draw = ImageDraw.Draw(mask_image)

        # Draw a polygon on the mask image using the mask coordinates
        draw.polygon(mask_array, fill=255)

        return mask_image

    def apply_mask(self, mask_array: "np.ndarray"):
        from PIL import Image

        mask_image = self.draw_mask(mask_array)

        # Apply the mask to the original image
        masked_image = Image.new("RGBA", self.image.size)
        masked_image.paste(self.image, mask=mask_image)

        # Find the bounding box of the masked region
        bbox = masked_image.getbbox()

        # Crop the image based on the bounding box
        segmented_image = masked_image.crop(bbox)

        return segmented_image

    def resize_image(self, image):
        image.thumbnail((self.resize, self.resize))
        if image.width != self.resize or image.height != self.resize:
            if image.width > image.height:
                width = self.resize
                height = int((self.resize / image.width) * image.height)
            else:
                width = int((self.resize / image.height) * image.width)
                height = self.resize
            image = image.resize((width, height))
        return image

    def segment(self):
        result = self.find_masks()
        if len(result.masks) == 0:
            yield (ReturnType.NO_MASK, None)
        else:
            for mask in result.masks:
                try:
                    masked_image = self.apply_mask(mask.xy[0])
                    if self.resize:
                        masked_image = self.resize_image(masked_image)
                    yield (ReturnType.SEGMENTED_IMAGE, masked_image)
                except:
                    yield (ReturnType.ERROR, None)


async def segment_handler(request: Request):
    """
    This handler takes an image as input, finds all objects in the image, and
    returns a zip file containing cropped images of each object.
    If only one object is found, it returns a single image instead of a zip
    file.

    If a resize parameter is passed, it resizes the cropped images to the
    specified size while maintaining the aspect ratio.

    Examples:
        curl -X POST --data-binary "@/path/to/image.jpg" http://localhost:8000/segment
        curl -X POST --data-binary "@/path/to/image.jpg" http://localhost:8000/segment/512
    """
    import boto3
    from PIL import Image

    resize = request.path_params.get("resize", None)

    global time_of_last_request
    time_of_last_request = datetime.utcnow()

    body = await request.body()
    image = Image.open(BytesIO(body))
    segmentator = Segmentator(image, resize)
    segmented = list(segmentator.segment())
    images = [image]
    for return_type, segmented_image in segmented:
        match return_type:
            case ReturnType.NO_MASK:
                return JSONResponse(
                    {"error": "No masks found"},
                    status_code=HTTPStatus.BAD_REQUEST,
                )
            case ReturnType.ERROR:
                continue
            case ReturnType.SEGMENTED_IMAGE:
                images.append(segmented_image)

    # If all masks errored out, return an error
    if len(images) == 0:
        return JSONResponse(
            {"error": "Error cropping image"},
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_config["endpoint"],
        aws_access_key_id=s3_config["aws_access_key_id"],
        aws_secret_access_key=s3_config["aws_secret_access_key"],
        aws_session_token=None,
    )

    file_names = []
    for segmented_image in images:
        bytes_stream = BytesIO()
        segmented_image.save(bytes_stream, "WEBP")
        bytes_stream.seek(0)
        file_name = uuid.uuid4().hex + ".webp"
        s3_client.upload_fileobj(bytes_stream, s3_config["bucket"], file_name)
        file_names.append(
            os.path.join(s3_config["endpoint"], s3_config["bucket"], file_name)
        )

    return JSONResponse({"file_names": file_names})


async def health_handler(request: Request):
    """
    This is somewhat of a weird health check handler. If no requests have been
    received in the last KILL_AFTER_SECONDS seconds, it returns an error and
    forces the container to restart. Otherwise, it returns a 200 OK.

    This is because the AI model is loaded into memory only when a request is
    received, and we want to free memory after a period of inactivity, since
    I don't expect this service to be used very often.
    """
    global time_of_last_request

    if time_of_last_request is None:
        return Response(status_code=HTTPStatus.OK)

    time_since_last_request = datetime.utcnow() - time_of_last_request
    if time_since_last_request.total_seconds() > KILL_AFTER_SECONDS:
        return Response(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

    return Response(status_code=HTTPStatus.OK)


app = Starlette(
    debug=False,
    routes=[
        Route("/health", health_handler),
        Route("/segment", segment_handler, methods=["POST"]),
        Route("/segment/{resize:int}", segment_handler, methods=["POST"]),
    ],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
