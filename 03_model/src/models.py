"""Model definitions for Assignment 1-1."""
import torch
from torch import nn


class MNISTMLP(nn.Module):
    """Required backbone: 784 -> 512 -> 128 -> 10, without dropout."""

    def __init__(self) -> None:
        super().__init__()
        self.fc1 = nn.Linear(784, 512)
        self.fc2 = nn.Linear(512, 128)
        self.fc3 = nn.Linear(128, 10)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        x = images.view(images.size(0), -1)
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.fc3(x)
