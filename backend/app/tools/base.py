from abc import ABC, abstractmethod
from pydantic import BaseModel

class BaseTool(ABC):
    name: str          
    description: str   

    class Input(BaseModel):
        pass

    class Output(BaseModel):
        pass

    @abstractmethod
    def run(self, params: "BaseTool.Input") -> "BaseTool.Output":
        pass
