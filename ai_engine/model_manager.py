class ModelManager:
    def __init__(self, model_name="qwen2.5-coder:7b"):
        self.model_name = model_name

    def get_model(self):
        return self.model_name
