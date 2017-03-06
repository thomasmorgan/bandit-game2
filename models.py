from sqlalchemy import Integer
from sqlalchemy.sql.expression import cast
from sqlalchemy.ext.hybrid import hybrid_property
from dallinger.networks import DiscreteGenerational
from dallinger.models import Info
from dallinger.nodes import Agent, Source
from dallinger.information import Gene
from dallinger.config import get_config
config = get_config()


class BanditGenerational(DiscreteGenerational):

    __mapper_args__ = {"polymorphic_identity": "bandit_generational"}

    def add_node(self, node):
        super(BanditGenerational, self).add_node(newcomer=node)
        node.receive()


class GeneticSource(Source):
    """ A source that initializes the genes of the first generation """

    __mapper_args__ = {"polymorphic_identity": "genetic_source"}

    def _what(self):
        return Gene

    def create_genes(self):
        if config.get('allow_memory'):
            MemoryGene(origin=self, contents=config.get('seed_memory'))
        else:
            MemoryGene(origin=self, contents=0)

        if config.get('allow_curiosity'):
            CuriosityGene(origin=self, contents=config.get('seed_curiosity'))
        else:
            CuriosityGene(origin=self, contents=1)


class Bandit(Source):
    """ a bandit that you can play with """

    __mapper_args__ = {"polymorphic_identity": "bandit"}

    @hybrid_property
    def num_arms(self):
        return int(self.property1)

    @num_arms.setter
    def num_arms(self, num_arms):
        self.property1 = repr(num_arms)

    @num_arms.expression
    def num_arms(self):
        return cast(self.property1, Integer)

    @hybrid_property
    def good_arm(self):
        return int(self.property2)

    @good_arm.setter
    def good_arm(self, good_arm):
        self.property2 = repr(good_arm)

    @good_arm.expression
    def good_arm(self):
        return cast(self.property2, Integer)

    @hybrid_property
    def bandit_id(self):
        return int(self.property3)

    @bandit_id.setter
    def bandit_id(self, bandit_id):
        self.property3 = repr(bandit_id)

    @bandit_id.expression
    def bandit_id(self):
        return cast(self.property3, Integer)


class MemoryGene(Gene):
    """ A gene that controls the time span of your memory """

    __mapper_args__ = {"polymorphic_identity": "memory_gene"}

    def _mutated_contents(self):
        if config.get('allow_memory'):
            if random.random() < 0.5:
                return max([int(self.contents) + random.sample([-1, 1], 1)[0], 0])
            else:
                return self.contents
        else:
            return 0


class CuriosityGene(Gene):
    """ A gene that controls your curiosity """

    __mapper_args__ = {"polymorphic_identity": "curiosity_gene"}

    def _mutated_contents(self):
        if config.get('allow_curiosity'):
            if random.random() < 0.5:
                return min([max([int(self.contents) + random.sample([-1, 1], 1)[0], 1]), 10])
            else:
                return self.contents
        else:
            return 1


class Pull(Info):
    """ An info representing a pull on the arm of a bandit """

    __mapper_args__ = {"polymorphic_identity": "pull"}

    @hybrid_property
    def check(self):
        return self.property1

    @check.setter
    def check(self, check):
        self.property1 = check

    @check.expression
    def check(self):
        return self.property1

    @hybrid_property
    def bandit_id(self):
        return int(self.property2)

    @bandit_id.setter
    def bandit_id(self, bandit_id):
        self.property2 = repr(bandit_id)

    @bandit_id.expression
    def bandit_id(self):
        return cast(self.property2, Integer)

    @hybrid_property
    def remembered(self):
        return self.property3

    @remembered.setter
    def remembered(self, remembered):
        self.property3 = remembered

    @remembered.expression
    def remembered(self):
        return self.property3

    @hybrid_property
    def tile(self):
        return int(self.property4)

    @tile.setter
    def tile(self, tile):
        self.property4 = repr(tile)

    @tile.expression
    def tile(self):
        return cast(self.property4, Integer)

    @hybrid_property
    def trial(self):
        return int(self.property5)

    @trial.setter
    def trial(self, trial):
        self.property5 = repr(trial)

    @trial.expression
    def trial(self):
        return cast(self.property5, Integer)


class BanditAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "bandit_agent"}

    @hybrid_property
    def generation(self):
        return int(self.property2)

    @generation.setter
    def generation(self, generation):
        self.property2 = repr(generation)

    @generation.expression
    def generation(self):
        return cast(self.property2, Integer)

    def update(self, infos):
        for info in infos:
            if isinstance(info, Gene):
                self.mutate(info_in=info)

    def calculate_fitness(self):
        my_decisions = Pull.query.filter_by(origin_id=self.id, check="false").all()
        my_checks = Pull.query.filter_by(origin_id=self.id, check="true").all()
        bandits = Bandit.query.filter_by(network_id=self.network_id).all()

        payoff = config.get('payoff')
        memory = int(self.infos(type=MemoryGene)[0].contents)
        curiosity = int(self.infos(type=CuriosityGene)[0].contents)

        correct_decisions = [d for d in my_decisions if [b for b in bandits if b.bandit_id == d.bandit_id][0].good_arm == int(d.contents)]

        # how much each unit of memory costs fitness
        memory_cost = config.get('n_trials')*config.get('payoff')/config.get('n_options')*0.1
        curiosity_cost = config.get('n_trials')*config.get('payoff')/config.get('n_options')*0.1
        pull_cost = config.get('payoff')/config.get('n_options')

        fitness = config.get('f_min') + len(correct_decisions)*payoff - memory*memory_cost - curiosity*curiosity_cost - len(my_checks)*pull_cost

        fitness = max([fitness, 0.001])
        fitness = ((1.0*fitness)*config.get('f_scale_factor'))**config.get('f_power_factor')
        self.fitness = fitness

    def _what(self):
        return Gene
