'''This module contains recurrent network structures.'''

import climate
import numpy as np
import numpy.random as rng
import theano
import theano.tensor as TT

from . import feedforward

logging = climate.get_logger(__name__)

FLOAT = theano.config.floatX


def batches(samples, labels=None, steps=100, batch_size=64):
    '''Return a callable that generates samples from a dataset.

    Parameters
    ----------
    samples : ndarray (time-steps, data-dimensions)
        An array of data. Rows in this array correspond to time steps, and
        columns to variables.
    labels : ndarray (time-steps, label-dimensions), optional
        An array of data. Rows in this array correspond to time steps, and
        columns to labels.
    steps : int, optional
        Generate samples of this many time steps. Defaults to 100.
    batch_size : int, optional
        Generate this many samples per call. Defaults to 64. This must match the
        batch_size parameter that was used when creating the recurrent network
        that will process the data.

    Returns
    -------
    callable :
        A callable that can be used inside a dataset for training a recurrent
        network.
    '''
    def unlabeled_sample():
        xs = np.zeros((steps, batch_size, samples.shape[1]), FLOAT)
        for i in range(batch_size):
            j = rng.randint(len(samples) - steps)
            xs[:, i, :] = samples[j:j+steps]
        return [xs]

    def labeled_sample():
        xs = np.zeros((steps, batch_size, samples.shape[1]), FLOAT)
        ys = np.zeros((steps, batch_size, labels.shape[1]), FLOAT)
        for i in range(batch_size):
            j = rng.randint(len(samples) - steps)
            xs[:, i, :] = samples[j:j+steps]
            ys[:, i, :] = labels[j:j+steps]
        return [xs, ys]

    return unlabeled_sample if labels is None else labeled_sample


class Autoencoder(feedforward.Autoencoder):
    '''An autoencoder network attempts to reproduce its input.
    '''

    def setup_vars(self):
        '''Setup Theano variables for our network.

        Returns
        -------
        vars : list of theano variables
            A list of the variables that this network requires as inputs.
        '''
        # the first dimension indexes time, the second indexes the elements of
        # each minibatch, and the third indexes the variables in a given frame.
        self.x = TT.tensor3('x')

        # the weights are the same shape as the output and specify the strength
        # of each entries in the error computation.
        self.weights = TT.tensor3('weights')

        if self.weighted:
            return [self.x, self.weights]
        return [self.x]


class Predictor(Autoencoder):
    '''A predictor network attempts to predict its next time step.
    '''

    def error(self, output):
        '''Build a theano expression for computing the network error.

        Parameters
        ----------
        output : theano expression
            A theano expression representing the output of the network.

        Returns
        -------
        error : theano expression
            A theano expression representing the network error.
        '''
        # we want the network to predict the next time step. if y is the output
        # of the network and f(y) gives the prediction, then we want f(y)[0] to
        # match x[1], f(y)[1] to match x[2], and so forth.
        err = self.x[1:] - self.generate_prediction(output)[:-1]
        if self.weighted:
            return (self.weights[1:] * err * err).sum() / self.weights[1:].sum()
        return (err * err).mean()

    def generate_prediction(self, y):
        '''Given outputs from each time step, map them to subsequent inputs.

        This defaults to the identity transform, i.e., the output from one time
        step is treated as the input to the next time step with no
        transformation. Override this method in a subclass to provide, e.g.,
        predictions based on random samples, lookups in a dictionary, etc.

        Parameters
        ----------
        y : theano variable
            A symbolic variable representing the "raw" output of the recurrent
            predictor.

        Returns
        -------
        y : theano variable
            A symbolic variable representing the inputs for the next time step.
        '''
        return y


class Regressor(feedforward.Regressor):
    '''A regressor attempts to produce a target output.'''

    def setup_vars(self):
        '''Setup Theano variables for our network.

        Returns
        -------
        vars : list of theano variables
            A list of the variables that this network requires as inputs.
        '''
        # the first dimension indexes time, the second indexes the elements of
        # each minibatch, and the third indexes the variables in a given frame.
        self.x = TT.tensor3('x')

        # for a regressor, this specifies the correct outputs for a given input.
        self.targets = TT.tensor3('targets')

        # the weights are the same shape as the output and specify the strength
        # of each entries in the error computation.
        self.weights = TT.tensor3('weights')

        if self.weighted:
            return [self.x, self.targets, self.weights]
        return [self.x, self.targets]


class Classifier(feedforward.Classifier):
    '''A classifier attempts to match a 1-hot target output.'''

    def setup_vars(self):
        '''Setup Theano variables for our network.

        Returns
        -------
        vars : list of theano variables
            A list of the variables that this network requires as inputs.
        '''
        # the first dimension indexes time, the second indexes the elements of
        # each minibatch, and the third indexes the variables in a given frame.
        self.x = TT.tensor3('x')

        # for a classifier, this specifies the correct labels for a given input.
        # the labels array for a recurrent network is (time_steps, batch_size).
        self.labels = TT.imatrix('labels')

        # the weights are the same shape as the output and specify the strength
        # of each entry in the error computation.
        self.weights = TT.matrix('weights')

        if self.weighted:
            return [self.x, self.labels, self.weights]
        return [self.x, self.labels]

    def error(self, output):
        '''Build a theano expression for computing the network error.

        Parameters
        ----------
        output : theano expression
            A theano expression representing the output of the network.

        Returns
        -------
        error : theano expression
            A theano expression representing the network error.
        '''
        lo = TT.cast(1e-5, FLOAT)
        hi = TT.cast(1, FLOAT)
        # flatten all but last components of the output and labels
        n = output.shape[0] * output.shape[1]
        correct = TT.reshape(self.labels, (n, ))
        weights = TT.reshape(self.weights, (n, ))
        prob = TT.reshape(output, (n, output.shape[2]))
        nlp = -TT.log(TT.clip(prob[TT.arange(n), correct], lo, hi))
        if self.weighted:
            return (weights * nlp).sum() / weights.sum()
        return nlp.mean()
