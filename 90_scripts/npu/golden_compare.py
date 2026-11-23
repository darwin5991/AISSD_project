"""Batched integer application reference, separate from RTL/bank addressing."""
import numpy as np

def wrap32(value):
    wide = np.asarray(value,dtype=np.int64)
    return ((wide + (1<<31)) & 0xffffffff) - (1<<31)

def infer(input8,weights,biases):
    q = np.asarray(input8,dtype=np.int8)
    outputs = []
    for i,(w,b,bs,shift) in enumerate(zip(weights,biases,(3,1,2),(10,7,7))):
        # int64 sum is exact for the fixed 784/512/128 signed INT8 dimensions.
        bias = wrap32(np.asarray(b,dtype=np.int64)<<bs)
        acc = wrap32(q.astype(np.int64) @ w.astype(np.int64).T + bias)
        if i<2:
            acc = np.maximum(acc,0)
        q = np.clip(acc>>shift,-128,127).astype(np.int8)
        outputs.append(q.copy())
    # numpy.argmax returns the first index on ties; only the 10 real classes.
    return np.argmax(q,axis=1).astype(np.uint32),outputs

def compare(predictions,golden,labels):
    pred = np.asarray(predictions,dtype=np.uint32).reshape(-1)
    golden = np.asarray(golden,dtype=np.uint32).reshape(-1)
    labels = np.asarray(labels,dtype=np.uint32).reshape(-1)
    if pred.shape!=golden.shape or pred.shape!=labels.shape or not len(pred):
        raise ValueError("prediction count mismatch")
    if np.any(pred>9):
        raise ValueError("invalid prediction/sentinel")
    mismatch = np.flatnonzero(pred!=golden)
    wrong = np.flatnonzero(pred!=labels)
    return dict(images=len(pred),golden_mismatches=len(mismatch),
                golden_match_percent=100.0*(len(pred)-len(mismatch))/len(pred),
                mismatch_indices=mismatch.tolist(),correct=int((pred==labels).sum()),
                accuracy_percent=100.0*int((pred==labels).sum())/len(pred),
                label_error_indices=wrong.tolist(),details=[
                    dict(image_index=int(i),rtl=int(pred[i]),golden=int(golden[i]),label=int(labels[i]))
                    for i in mismatch])
