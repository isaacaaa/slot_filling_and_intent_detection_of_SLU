"""Slot Tagger models."""
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.nn.utils.rnn as rnn_utils

class LSTMTagger(nn.Module):
    
    def __init__(self, embedding_dim, hidden_dim, vocab_size, tagset_size, bidirectional=True, num_layers=1, dropout=0., device=None, extFeats_dim=None):
        """Initialize model."""
        super(LSTMTagger, self).__init__()
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.vocab_size = vocab_size
        self.tagset_size = tagset_size
        #self.pad_token_idxs = pad_token_idxs
        self.bidirectional = bidirectional
        self.num_layers = num_layers
        self.dropout = dropout
        self.device = device
        self.extFeats_dim = extFeats_dim

        self.num_directions = 2 if self.bidirectional else 1
        self.dropout_layer = nn.Dropout(p=self.dropout)
        
        self.word_embeddings = nn.Embedding(self.vocab_size, self.embedding_dim)

        # The LSTM takes word embeddings as inputs, and outputs hidden states
        self.append_feature_dim = 0
        if self.extFeats_dim:
            self.append_feature_dim += self.extFeats_dim
            self.extFeats_linear = nn.Linear(self.append_feature_dim, self.append_feature_dim)
        else:
            self.extFeats_linear = None

        # with dimensionality hidden_dim.
        self.lstm = nn.LSTM(self.embedding_dim + self.append_feature_dim, self.hidden_dim, num_layers=self.num_layers, bidirectional=self.bidirectional, batch_first=True, dropout=self.dropout)
        
        # The linear layer that maps from hidden state space to tag space
        self.hidden2tag = nn.Linear(self.num_directions * self.hidden_dim, self.tagset_size)

        #self.init_weights()

    def init_weights(self, initrange=0.2):
        """Initialize weights."""
        self.word_embeddings.weight.data.uniform_(-initrange, initrange)
        #for pad_token_idx in self.pad_token_idxs:
        #    self.word_embeddings.weight.data[pad_token_idx].zero_()
        if self.extFeats_linear:
            self.extFeats_linear.weight.data.uniform_(-initrange, initrange)
            self.extFeats_linear.bias.data.uniform_(-initrange, initrange)
        for weight in self.lstm.parameters():
            weight.data.uniform_(-initrange, initrange)
        self.hidden2tag.weight.data.uniform_(-initrange, initrange)
        self.hidden2tag.bias.data.uniform_(-initrange, initrange)
    
    def forward(self, sentences, lengths, extFeats=None, with_snt_classifier=False, masked_output=None):
        # step 1: word embedding
        embeds = self.word_embeddings(sentences)
        if type(extFeats) != type(None):
            concat_input = torch.cat((embeds, self.extFeats_linear(extFeats)), 2)
        else:
            concat_input = embeds
        concat_input = self.dropout_layer(concat_input)
        
        # step 2: BLSTM encoder
        packed_embeds = rnn_utils.pack_padded_sequence(concat_input, lengths, batch_first=True)
        packed_lstm_out, packed_h_t_c_t = self.lstm(packed_embeds)  # bsize x seqlen x dim
        lstm_out, unpacked_len = rnn_utils.pad_packed_sequence(packed_lstm_out, batch_first=True)

        # step 3: slot tagger
        lstm_out_reshape = lstm_out.contiguous().view(lstm_out.size(0)*lstm_out.size(1), lstm_out.size(2))
        tag_space = self.hidden2tag(self.dropout_layer(lstm_out_reshape))
        tag_scores = F.log_softmax(tag_space, dim=1)
        tag_scores = tag_scores.view(lstm_out.size(0), lstm_out.size(1), tag_space.size(1))
        
        if with_snt_classifier:
            return tag_scores, (packed_h_t_c_t, lstm_out, lengths)
        else:
            return tag_scores
    
    def load_model(self, load_dir):
        if self.device.type == 'cuda':
            self.load_state_dict(torch.load(open(load_dir, 'rb')))
        else:
            self.load_state_dict(torch.load(open(load_dir, 'rb'), map_location=lambda storage, loc: storage))

    def save_model(self, save_dir):
        torch.save(self.state_dict(), open(save_dir, 'wb'))

