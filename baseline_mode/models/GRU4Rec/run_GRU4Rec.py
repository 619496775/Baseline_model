import sys
import os
from tqdm import tqdm
import pandas as pd
import argparse
sys.path.append('..')
sys.path.append('../..')
os.environ["CUDA_VISIBLE_DEVICES"]='1'
import tensorflow as tf
import numpy as np
from model_GRU4rec import GRU4Rec
from make_datasets import make_datasets
from DataInput import DataIterator
from evaluation import SortItemsbyScore,Metric_HR,Metric_MRR,Metric_NDCG


def parse_args():
    parser = argparse.ArgumentParser(description='DeepRec')
    parser.add_argument('--num_epochs', type=int, default=30)
    parser.add_argument('--emb_size', type=int, default=50)
    parser.add_argument('--len_Seq', type=int, default=5)
    parser.add_argument('--len_Tag', type=int, default=1)
    parser.add_argument('--len_Pred', type=int, default=1)
    parser.add_argument('--neg_sample', type=int, default=10)
    parser.add_argument('--batch_size', type=int, default=500)
    parser.add_argument('--layers', type=int, default=1)
    parser.add_argument('--learning_rate', type=float, default=1e-3)
    parser.add_argument('--keep_prob', type=float, default=0.7)
    parser.add_argument('--loss_fun', type=str, default='top1')
    parser.add_argument('--l2_lambda', type=float, default=1e-6)
    return parser.parse_args()

if __name__ == '__main__':

    # Get Params
    args = parse_args()
    len_Seq = args.len_Seq   #序列的长度
    len_Tag = args.len_Tag   #训练时目标的长度
    len_Pred = args.len_Pred     #预测时目标的长度
    batch_size = args.batch_size
    emb_size = args.emb_size
    neg_sample = args.neg_sample
    keep_prob = args.keep_prob
    layers = args.layers
    loss_fun = args.loss_fun
    l2_lambda = args.l2_lambda
    num_epochs = args.num_epochs
    learning_rate = args.learning_rate

    # make datasets

    print('==> make datasets <==')
    file_path = '../../datasets/ml-1m/ml-1m-item-f.txt'
    names = ['user', 'item', 'rateing', 'timestamps']
    data = pd.read_csv(file_path, header=None, sep=' ', names=names)
    d_train, d_test, d_info = make_datasets(data, len_Seq, len_Tag, len_Pred)
    num_usr, num_item, items_usr_clicked, _, _ = d_info
    all_items = [i for i in range(num_item)]

    # Define DataIterator

    trainIterator = DataIterator('train',d_train, batch_size, neg_sample,
                                 all_items, items_usr_clicked, shuffle=True)
    testIterator = DataIterator('test',d_test, batch_size,  shuffle=False)

    # Define Model

    model = GRU4Rec(emb_size, num_usr, num_item, len_Seq, 1, layers)
    loss = model.loss
    input_Seq = model.input_Seq
    input_NegT = model.input_NegT
    input_PosT = model.input_PosT
    input_keepprob = model.input_keepprob
    score_pred = model.predict()

    # Define Optimizer

    global_step = tf.Variable(0, trainable=False)
    update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    with tf.control_dependencies(update_ops):
        optimizer = tf.train.AdamOptimizer(learning_rate)
        tvars = tf.trainable_variables()
        grads, _ = tf.clip_by_global_norm(tf.gradients(loss, tvars), 5)
        grads_and_vars = tuple(zip(grads, tvars))
        train_op = optimizer.apply_gradients(grads_and_vars, global_step=global_step)

    # Training and test for every epoch

    f = open('log_ml@2022_6_20_lens=50.txt','w')

    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())

        for epoch in range(num_epochs):

            #train

            cost_list = []
            for train_input in tqdm(trainIterator,desc='epoch {}'.format(epoch),total=trainIterator.total_batch):
                batch_usr, batch_seq, batch_pos, batch_neg = train_input
                feed_dict = {input_Seq: batch_seq,input_PosT: batch_pos
                    , input_NegT: batch_neg,input_keepprob: keep_prob}
                _, step, cost= sess.run([train_op, global_step, loss],feed_dict)
                cost_list += list(cost)
            mean_cost = np.mean(cost_list)
            #saver.save(sess, FLAGS.save_path)

            # test

            pred_list = []
            next_list = []
            user_list = []

            for test_input in testIterator:
                batch_usr, batch_seq, batch_pos, batch_neg = test_input
                feed_dict = {input_Seq: batch_seq, input_keepprob: 1.0}
                pred = sess.run(score_pred, feed_dict)  # , options=options, run_metadata=run_metadata)

                pred_list += pred.tolist()
                next_list += list(batch_pos)
                user_list += list(batch_usr)

            sorted_items,sorted_score = SortItemsbyScore(next_list, all_items,pred_list,reverse=True,remove_hist=True
                                                   ,usr=user_list,usrclick=items_usr_clicked)
            #
            hr10 = Metric_HR(10, next_list, sorted_items)
            ndcg10 = Metric_NDCG(10, next_list, sorted_items)
            hr5 = Metric_HR(5, next_list, sorted_items)
            ndcg5 = Metric_NDCG(5, next_list, sorted_items)
            # Mrr = Metric_MRR(next_list,sorted_items)

            # f = open(file_path,'w')
            print(
                " epoch {}, mean_loss{:g}, test HR@10: {:g} NDCG@10: {:g},test HR@5: {:g} NDCG@5: {:g}"
                .format(epoch + 1, mean_cost, hr10, ndcg10, hr5, ndcg5))

            print(
                " epoch {}, mean_loss{:g}, test HR@10: {:g} NDCG@10: {:g},test HR@5: {:g} NDCG@5: {:g}"
                .format(epoch + 1, mean_cost, hr10, ndcg10, hr5, ndcg5),
                file=f)

            f.flush()

        f.close()