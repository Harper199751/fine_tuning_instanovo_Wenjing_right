#import the Python libraries and InstaNovo modules.
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import hydra
import torch
import torch.nn as nn
from omegaconf import DictConfig, OmegaConf

from instanovo.__init__ import console
from instanovo.common import AccelerateDeNovoTrainer, DataProcessor
from instanovo.inference import Decoder, GreedyDecoder
from instanovo.transformer.data import TransformerDataProcessor
from instanovo.transformer.model import InstaNovo
from instanovo.utils.colorlogging import ColorLog
from instanovo.utils.s3 import S3FileHandler

#sets up the logger and pathway
logger = ColorLog(console, __name__).logger

CONFIG_PATH = Path(__file__).parent.parent / "configs"


class TransformerTrainer(AccelerateDeNovoTrainer):
    
    def __init__(self, config: DictConfig) -> None: # define the initialization function
        super().__init__(config) #run the parent trainer

        self.loss_fn = nn.CrossEntropyLoss(ignore_index=0) #Define the loss function

        #define the building of model
    def setup_model(self) -> nn.Module:
        #set up model
        config = self.config.get("model", {}) #read settings of configuration
        model = InstaNovo( #creat the InstaNovo model based on the configuration
            residue_set=self.residue_set,
            dim_model=config["dim_model"],
            n_head=config["n_head"],
            dim_feedforward=config["dim_feedforward"],
            encoder_layers=config["encoder_layers"],
            decoder_layers=config["decoder_layers"],
            dropout=config["dropout"],
            max_charge=config["max_charge"],
            use_flash_attention=config["use_flash_attention"],
            conv_peak_encoder=config["conv_peak_encoder"],
            peak_embedding_dtype=config["peak_embedding_dtype"],
        )

        # only train peak_encoder and freeze other layers        
        # freeze parameters
        for name, param in model.named_parameters(): #back to name and para of each parameter
            param.requires_grad = False #run one direction

    
        for name, param in model.named_parameters(): #back to name and para of each parameter
            name_lower = name.lower() #transfer to lower case

            if "peak_encoder" in name_lower: #only open peak_encoder module
                param.requires_grad = True


        #count trainable and total amount of para
        trainable = 0 
        total = 0
        print("\n===== Trainable parameters after ultra-light freezing =====")
        for name, param in model.named_parameters(): 
            total += param.numel() #count all para
            if param.requires_grad: #count peak_encoder para
                trainable += param.numel()
                print(name, param.numel())

        print(f"Trainable params: {trainable:,} / {total:,} ({100 * trainable / total:.4f}%)")
        print("===== End freezing setup =====\n")
        return model

    #Update the vocabulary of the model checkpoint.
    def update_vocab(self, model_state: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]: 
        return self._update_vocab(  
            model_state,
            target_layers=["head.weight", "head.bias", "aa_embed.weight"],
            resolution=self.config.get("residue_conflict_resolution", "delete"),
        ) # handle vocabulary mismatch between checkpoint and current config, such as AGT and AGTT
    #Setup the optimizer.
    def setup_optimizer(self) -> torch.optim.Optimizer:
        trainable_params = [p for p in self.model.parameters() if p.requires_grad] #pick up the para of peak_encoder

        print(f"Optimizer trainable parameter tensors: {len(trainable_params)}")

        return torch.optim.Adam(
            trainable_params,
            lr=float(self.config["learning_rate"]), # set learning rate
            weight_decay=float(self.config.get("weight_decay", 0.0)), #regulate para too big
        )
        #use Adam optimizer to renew para based on loss only for peak_encoder
     
     #Setup the decoder
    def setup_decoder(self) -> Decoder:
        return GreedyDecoder(model=self.model, float_dtype=torch.float32 if self.config.get("mps", False) else torch.float64)
    
    #Setup the processor for datasets 
    def setup_data_processors(self) -> tuple[DataProcessor, DataProcessor]: #transfer data to tensor that trasformer could read
        train_processor = TransformerDataProcessor(
            self.residue_set, # set residue/protein vocabulary, filter the right range of data
            n_peaks=self.config.model.get("n_peaks", 200), #define the maxium amount of peaks
            min_mz=self.config.model.get("min_mz", 50.0), #define the min number of mz
            max_mz=self.config.model.get("max_mz", 2500.0), #define the maxium number of mz
            min_intensity=self.config.model.get("min_intensity", 0.01), #define the min number of intensity
            remove_precursor_tol=self.config.model.get("remove_precursor_tol", 2.0), # reduce the precursor position effects
            return_str=False,
            use_spectrum_utils=False,
        )
        #regulat the valid dataset are suitable for model input
        valid_processor = TransformerDataProcessor(
            self.residue_set,
            n_peaks=self.config.model.get("n_peaks", 200),
            min_mz=self.config.model.get("min_mz", 50.0),
            max_mz=self.config.model.get("max_mz", 2500.0),
            min_intensity=self.config.model.get("min_intensity", 0.01),
            remove_precursor_tol=self.config.model.get("remove_precursor_tol", 2.0),
            return_str=False,
            use_spectrum_utils=False,
        )

        return train_processor, valid_processor
    
    #save checkpoint and model
    def add_checkpoint_state(self) -> dict[str, Any]:
        return {}

    def save_model(self, is_best_checkpoint: bool = False) -> None:
        if not self.accelerator.is_main_process:
            return

        checkpoint_dir = self.config.get("model_save_folder_path", "./checkpoints")
        os.makedirs(checkpoint_dir, exist_ok=True)

       
        if self.config.get("keep_model_every_interval", False):
            model_path = os.path.join(checkpoint_dir, f"model_epoch_{self.epoch:02d}_step_{self.global_step + 1}.ckpt")
        else:
            model_path = os.path.join(checkpoint_dir, "model_latest.ckpt")
            if Path(model_path).exists() and Path(model_path).is_file():
                Path(model_path).unlink()

        unwrapped_model = self.accelerator.unwrap_model(self.model)

        checkpoint_state = {
            "state_dict": unwrapped_model.state_dict(),
            "config": OmegaConf.to_container(self.config.model),
            "residues": self.residue_set.residue_masses,
            "epoch": self.epoch,
            "global_step": self.global_step + 1,
        }
        checkpoint_state.update(self.add_checkpoint_state())

        torch.save(checkpoint_state, model_path)
        logger.info(f"Saved model to {model_path}")

        if S3FileHandler._aichor_enabled():
            self.s3.upload(model_path, S3FileHandler.convert_to_s3_output(model_path))

        if is_best_checkpoint and self.accelerator.is_main_process:
            best_model_path = os.path.join(checkpoint_dir, "model_best.ckpt")
            if Path(best_model_path).exists() and Path(best_model_path).is_file():
                Path(best_model_path).unlink()

            shutil.copy(model_path, best_model_path)

            if S3FileHandler._aichor_enabled():
                self.s3.upload(best_model_path, S3FileHandler.convert_to_s3_output(best_model_path))

        logger.info(f"Saved checkpoint to {model_path}")

    # set forward pass to calculate loss
    def forward(self, batch: Any) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        preds = self.model(
            x=batch["spectra"],
            p=batch["precursors"],
            y=batch["peptides"],
            x_mask=batch["spectra_mask"], # fill the length for each spectra
            y_mask=batch["peptides_mask"], # fill the length for each peptides
        )

        preds = preds[:, :-1].reshape(-1, preds.shape[-1]) #stretch 

        loss = self.loss_fn(preds, batch["peptides"].flatten()) #calculate loss

        return loss, {"loss": loss}
    
    # get predictions for a batch
    def get_predictions(self, batch: Any) -> tuple[list[str] | list[list[str]], list[str] | list[list[str]]]:
        # chose the highest possible prediction
        batch_predictions = self.decoder.decode(
            spectra=batch["spectra"],
            precursors=batch["precursors"],
            beam_size=self.config.get("n_beams", 1),
            max_length=self.config.get("max_length", 40),
        )
        
        # transfer to peptide sequence
        targets = [self.residue_set.decode(i, reverse=True) for i in batch["peptides"]]
        # return to predicted and real peptide
        return batch_predictions["predictions"], targets

# input the configuration info to class 
@hydra.main(config_path=str(CONFIG_PATH), version_base=None, config_name="instanovo") #read instanovo info
def main(config: DictConfig) -> None:
    #train the new model
    logger.info("Initializing training.")
    trainer = TransformerTrainer(config)
    trainer.train()


if __name__ == "__main__":
    main()
