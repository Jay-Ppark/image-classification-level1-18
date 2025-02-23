import torch
import pandas as pd
import numpy as np

from torch.utils.data import DataLoader

from itertools import product
import os

from data_set import MaskDataset
from model import PretrainedModel
from predict import Predictor
from utils import Label
from utils import get_time
from utils import tta_augmentation
import config

import glob

def tta(feature, model_path):
    tta_list = []
    for aug in tta_augmentation():
        tta_list.append(predict_and_save(feature, model_path, aug))
    tta_list.append(predict_and_save(feature, model_path))
    return tta_list

def predict_and_save(feature, path, transforms=None):
    test_df = pd.read_csv(config.test_csv)
    test_dataset = MaskDataset(
        test_df, config.test_dir, transforms=transforms, train=False
    )

    test_dataloader = DataLoader(
        dataset=test_dataset, batch_size=config.BATCH_SIZE, num_workers=2,
    )

    device = torch.device("cuda:0")
    label = Label()
    class_num = label.get_class_num(feature)

    print(f'loading {feature}({class_num}) model.. ')
    model = PretrainedModel(config.model_name, class_num).model
    model.load_state_dict(torch.load(path))
    print(f'load {feature}({class_num}) model!! ')

    model.to(device)
    predictor = Predictor(
        model, config.NUM_EPOCH, device, config.BATCH_SIZE, tta=config.tta
    )

    result = predictor.predict(test_dataloader, feature)

    return result

def main():
    model_path = glob.glob(
        os.path.join(config.model_dir, config.predict_dir, "*.pt")
        )
    print(model_path)

    result_list = []
    if config.merge_feature:
        result_list.append(predict_and_save(config.merge_feature_name, model_path[0]))
    else:
        for feature in config.features:
            for path in model_path:
                if feature in path:
                    break
            if config.tta:
                result_list.append(tta(feature, path))
            else:
                result_list.append(predict_and_save(feature, path))
    predict(result_list)



def predict(result):
    """
    result row
        0: age
        1: mask
        2: gender
    """
    mask = [0, 1, 2]
    gender = [0, 1]
    age = [0, 1, 2]

    label_number = list(product(mask, gender, age))
    print(label_number)

    submission = []
    if config.merge_feature:
        result = result[0]
        for i in range(len(result)):
            path = result[i][0]
            pred_class = result[i][1]

            submission.append([path, pred_class])
        result_df = pd.DataFrame.from_records(
            submission, columns=["ImageID", "ans"]
        )
    else:
        if config.tta:
            # soft voting
            soft_voting = []
            for feature_result in result:
                # feature result = (augmentation, data_num, data)
                feature_result = np.array(feature_result)
                preds = feature_result[:, :, 1]
                preds_list = []
                for t in preds:
                    preds_list.append(np.stack(t))
                preds_np = np.array(preds_list)

                soft_voting.append(preds_np)
            # soft_voting = np.array(soft_voting)

            # soft_voting에는 feature별 inferenec결과가 담겨있다.
            predict_result = []
            for feature_result in soft_voting:
                # 하나의 이미지에 대해서 class별 평균을 구한다.
                mean_np = np.mean(feature_result, axis=0)
                predict_result.append(np.argmax(mean_np, axis=-1))
            predict_result = np.array(predict_result)

            for i in range(len(result[0][0])):
                path = result[0][0][i][0]
                pred_class = label_number.index(
                    (predict_result[0][i], predict_result[1][i], predict_result[2][i])
                )
                submission.append([path.split(os.sep)[-1], pred_class])
            result_df = pd.DataFrame.from_records(
                submission, columns=["ImageID", "ans"]
            )
        else:
            for i in range(len(result[0])):
                path = result[0][i][0]
                pred_class = label_number.index(
                    (result[0][i][1], result[1][i][1], result[2][i][1])
                )
                submission.append([path.split(os.sep)[-1], pred_class])
            result_df = pd.DataFrame.from_records(
                submission, columns=["ImageID", "ans"]
            )

    result_df.to_csv(
        f"{config.model_name}-{get_time()}-submission.csv", index=False
    )

import time
if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print('elapsed time =', (end-start) / 60)
