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
import paddlefsl.utils as utils
import numpy as np


def inner_adapt(feature_model,
                head_layer,
                data,
                loss_fn,
                inner_lr,
                steps=1,
                approximate=True):
    """
    Take several adaptation steps for a model, known as inner adaptation or fast adaptation in ANIL.

    Args:
        feature_model(paddle.nn.Layer): feature model under training.
        head_layer(paddle.nn.Layer): head layer of the model under training.
        data(Tuple): in the form of ((support_data, support_labels), (query_data, query_labels)), data and labels
            can be numpy array or paddle.Tensor.
        loss_fn(paddle.nn.{LossFunction}): loss function.
        inner_lr(float): inner learning rate, also known as fast learning rate.
        steps(int, optional): adaptation steps, default 1.
        approximate(bool, optional): whether to use first order approximate during meta-training, default True.
            currently we only support first order approximate version of MAML, because paddle do not support second
            order gradients of several operations.

    Returns:
        valid_loss, valid_acc(paddle.Tensor): inner validation loss and accuracy, also known as query loss.

    Examples:
        ..code-block:: python

            from paddlefsl.model_zoo import anil

            img1, label1 = paddle.ones(shape=(1, 1, 2, 2), dtype='float32'), paddle.to_tensor([[0]], dtype='int64')
            img2, label2 = paddle.zeros(shape=(1, 1, 2, 2), dtype='float32'), paddle.to_tensor([[1]], dtype='int64')
            feature_model = paddle.nn.Sequential(
                paddle.nn.Flatten(),
                paddle.nn.Linear(4, 4)
            )
            head_layer = paddle.nn.Linear(4, 2)
            loss_fn = paddle.nn.CrossEntropyLoss()
            data = ((img1, label1), (img2, label2))
            anil.inner_adapt(feature_model, head_layer, data, loss_fn, 0.4)

    """
    # Unzip data and turn them into paddle.Tensor add pass the feature_model
    (support_data, support_labels), (query_data, query_labels) = data
    support_features = feature_model(paddle.to_tensor(support_data, dtype='float32'))
    query_features = feature_model(paddle.to_tensor(query_data, dtype='float32'))
    support_labels, query_labels = paddle.to_tensor(support_labels), paddle.to_tensor(query_labels)
    # Adapt the head layer
    for step in range(steps):
        loss = loss_fn(head_layer(support_features), support_labels)
        utils.manual_gradient_descent(head_layer, inner_lr, loss, approximate)
    # Evaluate the adapted model
    predictions = head_layer(query_features)
    valid_loss = loss_fn(predictions, query_labels)
    valid_acc = utils.classification_acc(predictions, query_labels)
    return valid_loss, valid_acc


def meta_training(train_dataset,
                  valid_dataset,
                  feature_model,
                  head_layer,
                  meta_lr=0.002,
                  inner_lr=0.4,
                  iterations=60000,
                  meta_batch_size=32,
                  ways=5,
                  shots=5,
                  inner_adapt_steps=1,
                  approximate=True,
                  report_iter=10,
                  save_model_iter=5000,
                  save_model_root='~/paddlefsl_models'):
    """
    Implementation of ANIL(Almost No Inner Loop) algorithm, meta-training.
    ANIL is introduced by Aniruddh Raghu et al. in 2020[1]. It is an improved method of MAML.
    This function trains the given feature_model and head_layer with given datasets and hyper-parameters.

    .. note::
        Currently we only support first order approximate version of ANIL, because paddle do not support second
        order gradients of several operations.

    Refs:
        1.Raghu A, Raghu M, Bengio S, et al. 2020. "Rapid learning or feature reuse? towards understanding
        the effectiveness of maml" ICML.

    Args:
        train_dataset(paddlefsl.vision.dataset.FewShotDataset): dataset for meta-training.
        valid_dataset(paddlefsl.vision.dataset.FewShotDataset): dataset for meta-validation.
        feature_model(paddle.nn.Layer): feature model under training.
        head_layer(paddle.nn.Layer): head layer of the model under training.
        meta_lr(float, optional): meta learning rate, also known as outer learning rate, default 0.002.
        inner_lr(float, optional): inner learning rate, also known as fast learning rate, default 0.4.
        iterations(int, optional): meta-training iterations, default 60000.
        meta_batch_size(int, optional): number of tasks in one training iteration, default 32.
        ways(int, optional): number of classes in a task, default 5.
        shots(int, optional): number of training samples per class, default 5.
        inner_adapt_steps(int, optional): inner adaptation steps during training, default 1.
        approximate(bool, optional): whether to use first order approximate during meta-training, default True.
            currently we only support first order approximate version of MAML, because paddle do not support second
            order gradients of several operations.
        report_iter(int, optional): number of iterations between printing two reports, default 10.
        save_model_iter(int, optional): number of iterations between saving two model statuses, default 5000.
        save_model_root(str, optional): root directory to save model statuses, default '~/paddlefsl_models'

    Returns:
        str: directory where model statuses are saved. This function reports the loss and accuracy every 'report_iter'
            iterations in terminal as well as in 'training_report.txt' file. This function saves model status every
            'save_model_iter' iterations as 'iteration_x_feature.params' and 'iteration_x_head.params'.

    """
    # Set training configuration information and
    module_info = utils.get_info_str('anil', train_dataset, feature_model, str(ways) + 'ways', str(shots) + 'shots')
    train_info = utils.get_info_str('metaLR' + str(meta_lr), 'innerLR' + str(inner_lr),
                                    'batchSize' + str(meta_batch_size), 'approximate' if approximate else '')
    # Make directory to save report and parameters
    module_dir = utils.process_root(save_model_root, module_info)
    train_dir = utils.process_root(module_dir, train_info)
    report_file = train_dir + '/training_report.txt'
    utils.clear_file(report_file)
    # Set training methods
    feature_model.train()
    head_layer.train()
    all_params = list(feature_model.parameters()) + list(head_layer.parameters())
    scheduler = paddle.optimizer.lr.CosineAnnealingDecay(learning_rate=meta_lr, T_max=iterations)
    meta_opt = paddle.optimizer.Adam(parameters=all_params, learning_rate=scheduler)
    loss_fn = paddle.nn.CrossEntropyLoss()
    # Meta training iterations
    for iteration in range(iterations):
        # Clear gradient, loss and accuracy
        meta_opt.clear_grad()
        train_loss, train_acc, valid_loss, valid_acc = 0.0, 0.0, 0.0, 0.0
        for task_i in range(meta_batch_size):
            # Clone the head layer in order to keep connected with the original computation graph
            head_cloned = utils.clone_model(head_layer)
            # Sample a task from dataset
            task = train_dataset.sample_task_set(ways=ways, shots=shots)
            # Do inner adaptation
            data = (task.support_data, task.support_labels), (task.query_data, task.query_labels)
            inner_valid_loss, inner_valid_acc = inner_adapt(feature_model=feature_model,
                                                            head_layer=head_cloned,
                                                            data=data,
                                                            loss_fn=loss_fn,
                                                            inner_lr=inner_lr,
                                                            steps=inner_adapt_steps,
                                                            approximate=approximate)
            # Renew original model parameters using inner validation loss
            inner_valid_loss.backward(retain_graph=True)
            # Accumulate inner validation loss and inner validation accuracy
            train_loss += inner_valid_loss.numpy().item()
            train_acc += inner_valid_acc
            # Do the same adaptation using validation dataset
            if (iteration + 1) % report_iter == 0 or iteration + 1 == iterations:
                head_cloned = utils.clone_model(head_layer)
                task = valid_dataset.sample_task_set(ways, shots)
                data = (task.support_data, task.support_labels), (task.query_data, task.query_labels)
                loss_acc = inner_adapt(feature_model, head_cloned, data, loss_fn,
                                       inner_lr, inner_adapt_steps * 2, approximate)
                valid_loss += loss_acc[0].numpy().item()
                valid_acc += loss_acc[1]
        meta_opt.step()
        scheduler.step()
        # Print report and save report
        if (iteration + 1) % report_iter == 0 or iteration + 1 == iterations:
            utils.print_training_info(iteration=iteration + 1,
                                      train_loss=train_loss / meta_batch_size,
                                      train_acc=train_acc / meta_batch_size,
                                      valid_loss=valid_loss / meta_batch_size,
                                      valid_acc=valid_acc / meta_batch_size,
                                      report_file=report_file,
                                      info=[module_info, train_info])
        # Save model parameters
        if (iteration + 1) % save_model_iter == 0 or iteration + 1 == iterations:
            paddle.save(feature_model.state_dict(), train_dir + '/iteration' + str(iteration + 1) + 'feature.params')
            paddle.save(head_layer.state_dict(), train_dir + '/iteration' + str(iteration + 1) + 'head.params')
    return train_dir, feature_model, head_layer


def meta_testing(feature_model,
                 head_layer,
                 test_dataset,
                 test_epoch=10,
                 test_batch_size=32,
                 ways=5,
                 shots=5,
                 inner_lr=0.4,
                 inner_adapt_steps=1,
                 approximate=False):
    """
    Implementation of ANIL(Almost No Inner Loop) algorithm, meta-testing.

    Args:
        feature_model(paddle.nn.Layer): feature model under testing.
        head_layer(paddle.nn.Layer): head layer of the model under testing.
        test_dataset(paddlefsl.vision.dataset.FewShotDataset): dataset for meta-testing.
        test_epoch(int, optional): testing epoch number, default 10.
        test_batch_size(int, optional): tasks per testing epoch, default 32.
        ways(int, optional): number of classes in a task, default 5.
        shots(int, optional): number of training samples per class, default 5.
        inner_lr(float, optional): inner learning rate, also known as fast learning rate, default 0.4.
        inner_adapt_steps(int, optional): inner adaptation steps during testing, default 3.
        approximate(bool, optional): whether to use first order approximate during meta-training, default True.
            currently we only support first order approximate version of MAML, because paddle do not support second
            order gradients of several operations.

    Returns:
        None. This function prints the testing results, including accuracy in each epoch and the average accuracy.

    """
    module_info = utils.get_info_str('anil', test_dataset, feature_model, str(ways) + 'ways', str(shots) + 'shots')
    loss_fn = paddle.nn.CrossEntropyLoss()
    loss, acc = [], []
    for epoch in range(test_epoch):
        test_loss, test_acc = 0.0, 0.0
        for task_i in range(test_batch_size):
            head_cloned = utils.clone_model(head_layer)
            task = test_dataset.sample_task_set(ways=ways, shots=shots)
            data = (task.support_data, task.support_labels), (task.query_data, task.query_labels)
            inner_loss, inner_acc = inner_adapt(feature_model, head_cloned, data, loss_fn,
                                                inner_lr, inner_adapt_steps, approximate)
            test_loss += inner_loss.numpy().item()
            test_acc += inner_acc
        test_loss, test_acc = test_loss / test_batch_size, test_acc / test_batch_size
        loss.append(test_loss)
        acc.append(test_acc)
        print('Test Epoch', epoch, [module_info], 'Loss', test_loss, '\t', 'Accuracy', test_acc)
    print('Test finished', [module_info])
    print('Test Loss', np.mean(loss), '\tTest Accuracy', np.mean(acc), '\tStd', np.std(acc))
