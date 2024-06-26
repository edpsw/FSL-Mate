# Copyright 2021 PaddleFSL Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import paddle
import paddlefsl
from paddlefsl.model_zoo import ptuning

# Set computing device
paddle.set_device('gpu:0')


TASK_NAME = 'tnews'
LANGUAGE = 'zh'
MODEL_NAME = 'ernie-1.0'
DATA_PATH = ''
LEARNING_RATE = 1e-5
EPOCHS = 10
BATCH_SIZE = 16
SAVE_DIR = 'checkpoint/'
MAX_SEQ_LENGTH = 256
WARMUP_PROPORTION = 0.0
WEIGHT_DECAY = 0.0
SEED = 1000

def main():
    model, tokenizer, test_dataloader, label_dict = ptuning.do_train(model_name=MODEL_NAME,
                                                                 lan=LANGUAGE,
                                                                 task_name=TASK_NAME,
                                                                 save_dir=SAVE_DIR,
                                                                 learning_rate=LEARNING_RATE,
                                                                 batch_size=BATCH_SIZE,
                                                                 data_path = DATA_PATH,
                                                                 max_seq_length=MAX_SEQ_LENGTH,
                                                                 init_from_ckpt = None,
                                                                 warmup_proportion = WARMUP_PROPORTION,
                                                                 weight_decay = WEIGHT_DECAY,
                                                                 epochs = EPOCHS,
                                                                 seed = SEED)

    state_dict = paddle.load(SAVE_DIR + 'model/model_state.pdparams')
    model.set_dict(state_dict)

    test_acc = ptuning.do_evaluate(  model=model,
                                    lan=LANGUAGE,
                                    tokenizer=tokenizer,
                                    data_loader=test_dataloader,
                                    label_normalize_dict=label_dict)
    print('test accuracy:', test_acc)

if __name__ == '__main__':
    main()
